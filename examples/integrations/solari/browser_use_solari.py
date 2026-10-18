"""Run a Browser Use agent on a Solari-managed Chrome session."""

import asyncio
import gzip
import math
import os
import time
from pathlib import Path

from solari_browser import Solari  # type: ignore

from browser_use import Agent, Browser, ChatBrowserUse


def env_flag(name: str, *, default: bool = False) -> bool:
	"""Read a strict boolean environment variable."""
	value = os.getenv(name)
	if value is None:
		return default
	if value.lower() in {'1', 'true', 'yes', 'on'}:
		return True
	if value.lower() in {'0', 'false', 'no', 'off'}:
		return False
	raise ValueError(f'{name} must be true or false.')


async def download_recording(client: Solari, session_id: str, output: Path, *, timeout_seconds: float = 60) -> None:
	"""Download a native Solari rrweb replay after session release."""
	deadline = time.monotonic() + timeout_seconds
	while True:
		try:
			replay = await client.sessions.download_replay(session_id)
			if not replay:
				raise RuntimeError('Solari returned an empty recording.')
			if not replay.startswith(b'\x1f\x8b'):
				replay = gzip.compress(replay)
			output.parent.mkdir(parents=True, exist_ok=True)
			output.write_bytes(replay)
			print(f'Solari recording saved to {output} ({len(replay)} bytes)')
			return
		except Exception as error:
			if getattr(error, 'status', None) != 404 or time.monotonic() >= deadline:
				raise
			await asyncio.sleep(1)


async def enable_captcha_waiting(browser: Browser) -> None:
	"""Subscribe after Browser Use has registered its CAPTCHA watchdog."""
	await browser.cdp_client.send_raw('Solari.enableCaptchaEvents')


async def main() -> None:
	api_key = os.getenv('SOLARI_API_KEY', '').strip()
	if not api_key:
		raise RuntimeError('SOLARI_API_KEY is required.')

	stealth = env_flag('SOLARI_STEALTH')
	captcha = env_flag('SOLARI_CAPTCHA')
	recording = env_flag('SOLARI_RECORDING')
	if captcha and not stealth:
		raise RuntimeError('CAPTCHA waiting requires SOLARI_STEALTH=true.')
	if recording and not stealth:
		raise RuntimeError('Native Solari recording requires SOLARI_STEALTH=true.')
	step_timeout = 180
	if captcha:
		# Browser Use otherwise waits 120s; Solari allows a 200s solver request
		# plus injection. Preserve an explicitly configured customer timeout.
		if not os.getenv('TIMEOUT_CaptchaSolverWait'):
			os.environ['TIMEOUT_CaptchaSolverWait'] = '240'
		wait_timeout = float(os.environ['TIMEOUT_CaptchaSolverWait'])
		if not math.isfinite(wait_timeout) or wait_timeout < 0:
			raise ValueError('TIMEOUT_CaptchaSolverWait must be a finite, non-negative number.')
		# The wait runs inside Agent's outer per-step timeout, which otherwise
		# expires at 180s. Leave the normal 180s work budget after waiting.
		step_timeout += math.ceil(wait_timeout)

	client = Solari(
		api_key=api_key,
		region=os.getenv('SOLARI_REGION', 'us-west'),
		base_url=os.getenv('SOLARI_BASE_URL') or None,
	)
	session = None
	browser = None
	released = False
	try:
		session = await client.sessions.create(
			profile_id=os.getenv('SOLARI_PROFILE_ID') or None,
			stealth=stealth,
			captcha=captcha,
			recording=recording,
		)
		# The signed CDP endpoint is passed directly to Browser Use and is never logged.
		browser = Browser(cdp_url=session.cdp_endpoint, keep_alive=True)
		if captcha:
			await browser.start()
			await enable_captcha_waiting(browser)
		agent = Agent(
			task=os.getenv(
				'BROWSER_USE_TASK',
				'Open https://example.com and report the page heading.',
			),
			llm=ChatBrowserUse(),
			browser=browser,
			step_timeout=step_timeout,
		)
		history = await agent.run(max_steps=int(os.getenv('BROWSER_USE_MAX_STEPS', '10')))
		print(history.final_result())

		await browser.stop()
		browser = None
		await client.sessions.release_and_wait(session.id)
		released = True

		if recording:
			output = Path(os.getenv('SOLARI_RECORDING_PATH', 'solari-recording.rrweb.ndjson.gz'))
			await download_recording(client, session.id, output)
	finally:
		if browser is not None:
			try:
				await browser.stop()
			except Exception:
				pass
		if session is not None and not released:
			try:
				await client.sessions.release_and_wait(session.id)
			except Exception:
				pass
		await client.close()


if __name__ == '__main__':
	asyncio.run(main())
