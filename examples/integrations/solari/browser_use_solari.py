"""Run a Browser Use agent on a Solari-managed Chrome session."""

import asyncio
import gzip
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


async def main() -> None:
	api_key = os.getenv('SOLARI_API_KEY', '').strip()
	if not api_key:
		raise RuntimeError('SOLARI_API_KEY is required.')

	stealth = env_flag('SOLARI_STEALTH')
	recording = env_flag('SOLARI_RECORDING')
	if recording and not stealth:
		raise RuntimeError('Native Solari recording requires SOLARI_STEALTH=true.')

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
			recording=recording,
		)
		# The signed CDP endpoint is passed directly to Browser Use and is never logged.
		browser = Browser(cdp_url=session.cdp_endpoint, keep_alive=True)
		agent = Agent(
			task=os.getenv(
				'BROWSER_USE_TASK',
				'Open https://example.com and report the page heading.',
			),
			llm=ChatBrowserUse(),
			browser=browser,
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
