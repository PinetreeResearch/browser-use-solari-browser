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
uv run --with solari-browser==0.1.2 \
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
| `SOLARI_RECORDING` | `false` | Request a native rrweb session recording |
| `SOLARI_RECORDING_PATH` | `solari-recording.rrweb.ndjson.gz` | Recording output path |

The default fast browser is appropriate when recording is not needed. Native Solari recording is supported on stealth browsers, so the example requires both flags together:

```bash
export SOLARI_STEALTH=true
export SOLARI_RECORDING=true
uv run --with solari-browser==0.1.2 \
  python examples/integrations/solari/browser_use_solari.py
```

After session release, the example waits for the replay and saves a gzipped rrweb event stream.

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
git merge --ff-only upstream/main  # when the fork has no local commits to merge
```

When the Solari example adds commits on top of upstream, merge or rebase those commits after fetching and rerun the example smoke test before publishing.
