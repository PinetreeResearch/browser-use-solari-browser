# Browser Use × Solari Browser

Run the open-source Browser Use agent on a managed Solari Chrome session. Browser Use provides the agent loop and browser tools; Solari provides the remote browser and its session lifecycle. The two connect through Browser Use's standard `cdp_url` interface, so no Browser Use core code is changed.

## Install

From the repository root:

```bash
uv sync
```

Set the two required API keys:

```bash
export BROWSER_USE_API_KEY='...'
export SOLARI_API_KEY='...'
```

Run the example:

```bash
uv run --with solari-browser==0.2.1 \
  python examples/integrations/solari/browser_use_solari.py
```

The example creates one Solari Browser session, passes its signed CDP endpoint directly to Browser Use, runs the agent, disconnects Browser Use, and releases the Solari session in a `finally` block. API keys and signed endpoints are never printed or written to artifacts.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `BROWSER_USE_TASK` | Report the Example Domain heading | Agent task |
| `BROWSER_USE_MAX_STEPS` | `10` | Agent step limit |
| `SOLARI_REGION` | `us-west` | Solari browser region |
| `SOLARI_BASE_URL` | SDK default | Optional alternate API endpoint |
| `SOLARI_PROFILE_ID` | unset | Optional persistent Solari browser profile |
| `SOLARI_STEALTH` | `false` | Use a stealth browser |
| `SOLARI_CAPTCHA` | `false` | Enable CAPTCHA solving and Browser Use's CAPTCHA waiting on a stealth browser |
| `TIMEOUT_CaptchaSolverWait` | `240` when CAPTCHA is enabled | Maximum CAPTCHA wait in seconds; an explicit value is preserved |
| `SOLARI_RECORDING` | `false` | Request a native rrweb session recording |
| `SOLARI_RECORDING_PATH` | `solari-recording.rrweb.ndjson.gz` | Recording output path |

The default fast browser is appropriate when recording is not needed. Native Solari recording is supported on stealth browsers, so the example requires both flags together:

```bash
export SOLARI_STEALTH=true
export SOLARI_RECORDING=true
uv run --with solari-browser==0.2.1 \
  python examples/integrations/solari/browser_use_solari.py
```

After session release, the example waits for the replay and saves a gzipped rrweb event stream.

## CAPTCHA solving

Enable both flags to request a solver and let the agent wait for it:

```bash
export SOLARI_STEALTH=true
export SOLARI_CAPTCHA=true
uv run --with solari-browser==0.2.1 \
  python examples/integrations/solari/browser_use_solari.py
```

This requires a Solari pool that supports the `Solari.enableCaptchaEvents` CDP command. The example enables events after Browser Use connects and registers its CAPTCHA watchdog. The pool replays any ongoing solve, then emits `BrowserUse.captchaSolverStarted` and `BrowserUse.captchaSolverFinished`. Concurrent solves keep the agent waiting until all have finished. A successful event means the token was applied or the press-and-hold widget cleared; it does not guarantee that the website accepted the session.

The 240-second wait covers Solari's 200-second solver request budget plus token injection. Set `TIMEOUT_CaptchaSolverWait` to override it. The example also adds that wait budget to the agent's normal 180-second step timeout (420 seconds by default), so the outer timeout does not cancel an ongoing wait. The pool's independent CDP action safeguards remain active during a solve. Solver credits and provider support are still required; these flags do not bypass every anti-bot block.

## Use another Browser Use model

The example follows Browser Use's recommended `ChatBrowserUse()` setup. Any Browser Use-supported model can replace it without changing the Solari browser integration. For example, install the AWS extra and use `ChatAWSBedrock` if the agent should run on Amazon Bedrock:

```bash
uv sync --extra aws
```

```python
from browser_use.llm import ChatAWSBedrock

llm = ChatAWSBedrock(
	model='us.anthropic.claude-sonnet-4-6',
	aws_region='us-west-2',
)
```

## Updating this fork

Keep Solari-specific changes isolated to this directory so upstream Browser Use updates remain easy to merge:

```bash
git fetch upstream
git checkout main
git merge upstream/main
uv run pre-commit run --files \
  examples/integrations/solari/README.md \
  examples/integrations/solari/browser_use_solari.py
git push origin main
```

Resolve any merge conflicts in the isolated Solari example, then rerun the real example smoke test before publishing. GitHub's **Sync fork** button can also pull upstream changes when there are no conflicts.
