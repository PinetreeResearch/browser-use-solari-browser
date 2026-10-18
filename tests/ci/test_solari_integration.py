"""Exercise the optional Solari example with local HTTP and CDP servers."""

import asyncio
import json
import os

import pytest
from cdp_use import CDPClient
from pytest_httpserver import HTTPServer
from websockets.asyncio.server import ServerConnection, serve

solari_browser = pytest.importorskip('solari_browser')

from browser_use import Browser
from browser_use.browser.events import BrowserConnectedEvent, BrowserStoppedEvent
from browser_use.browser.watchdogs.captcha_watchdog import CaptchaWatchdog
from examples.integrations.solari.browser_use_solari import enable_captcha_waiting, main


@pytest.fixture
def solari_env(monkeypatch: pytest.MonkeyPatch, httpserver: HTTPServer) -> None:
	"""Keep all session requests on the local test server."""
	for key in ('SOLARI_PROFILE_ID', 'SOLARI_STEALTH', 'SOLARI_CAPTCHA', 'SOLARI_RECORDING', 'TIMEOUT_CaptchaSolverWait'):
		monkeypatch.delenv(key, raising=False)
	monkeypatch.setenv('SOLARI_API_KEY', 'local-test-key')
	monkeypatch.setenv('SOLARI_BASE_URL', httpserver.url_for('/'))


@pytest.mark.parametrize('captcha', [False, True])
@pytest.mark.parametrize('wait_timeout', [None, '300'])
async def test_solari_session_sends_captcha_option(
	captcha: bool, wait_timeout: str | None, solari_env: None, monkeypatch: pytest.MonkeyPatch, httpserver: HTTPServer
) -> None:
	monkeypatch.setenv('SOLARI_STEALTH', 'true')
	monkeypatch.setenv('SOLARI_CAPTCHA', str(captcha).lower())
	monkeypatch.setenv('TIMEOUT_CaptchaSolverWait', wait_timeout or '')
	body = {'stealth': True, **({'captcha': True} if captcha else {})}
	# Stop after real SDK serialization, before any browser or LLM is created.
	httpserver.expect_oneshot_request('/sessions', method='POST', json=body).respond_with_json(
		{'error': 'Local request capture complete'}, status=400
	)
	with pytest.raises(solari_browser.SolariError):
		await main()
	httpserver.check_assertions()
	if captcha:
		assert os.getenv('TIMEOUT_CaptchaSolverWait') == (wait_timeout or '240')


async def test_captcha_requires_stealth_before_creating_session(solari_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv('SOLARI_CAPTCHA', 'true')
	with pytest.raises(RuntimeError, match='SOLARI_STEALTH=true'):
		await main()


@pytest.mark.parametrize('success', [False, True])
async def test_real_captcha_watchdog_waits_for_solari_events(success: bool) -> None:
	finish = asyncio.Event()

	async def handler(connection: ServerConnection) -> None:
		request = json.loads(await connection.recv())
		assert request['method'] == 'Solari.enableCaptchaEvents'
		# Replaying an ongoing solve before acknowledging the subscription must
		# work: the watchdog is already registered at this point.
		info = {'vendor': 'recaptcha_v2', 'url': 'http://localhost/challenge', 'targetId': 'page', 'startedAt': 1}
		await connection.send(json.dumps({'method': 'BrowserUse.captchaSolverStarted', 'params': info}))
		await connection.send(json.dumps({'id': request['id'], 'result': {}}))
		await finish.wait()
		await connection.send(
			json.dumps(
				{
					'method': 'BrowserUse.captchaSolverFinished',
					'params': {**info, 'success': success, 'durationMs': 10, 'finishedAt': 11},
				}
			)
		)
		await connection.wait_closed()

	async with serve(handler, '127.0.0.1', 0) as server:
		port = next(iter(server.sockets)).getsockname()[1]
		url = f'ws://127.0.0.1:{port}'
		client = CDPClient(url)
		browser = Browser(cdp_url=url)
		browser._cdp_client_root = client
		watchdog = CaptchaWatchdog(browser_session=browser, event_bus=browser.event_bus)
		await client.start()
		try:
			await watchdog.on_BrowserConnectedEvent(BrowserConnectedEvent(cdp_url=url))
			await enable_captcha_waiting(browser)
			waiting = asyncio.create_task(watchdog.wait_if_captcha_solving(timeout=1))
			await asyncio.sleep(0)
			assert not waiting.done()
			finish.set()
			result = await asyncio.wait_for(waiting, 2)
			assert result is not None
			assert result.result == ('success' if success else 'failed')
			assert await watchdog.wait_if_captcha_solving(timeout=1) is None
		finally:
			finish.set()
			await client.stop()
			await watchdog.on_BrowserStoppedEvent(BrowserStoppedEvent())
			await browser.event_bus.stop(clear=True, timeout=1)
