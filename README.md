# StoryDesk

**Explainable match intelligence for broadcast: every claim links to the events that prove it.**

Built for the *Inside the Game: Developer Hackathon* (Microsoft x Premier League). StoryDesk turns a stream of **synthetic** football events into key moments, plain-language stories for different viewers, and timed broadcast overlays, and it refuses to publish any claim it cannot back with evidence.

> All data is synthetic. Teams (Northbridge, Eastvale) and players are fictional. No real match data, logos or likenesses are used.

## The problem

AI match summaries sound confident, but a broadcaster cannot put a number on screen unless it is right. StoryDesk treats explanation as something that must be **verifiable**, not just fluent.

## What it does

- **Simulates matches** with known ground truth: each match has three planted tactical events (a high press, a momentum swing, a big chance).
- **Detects key moments** with deterministic analytics (no AI): high press, momentum swing, big chances, goals.
- **Writes the story** (Narrator) and **checks it** (Verifier). Every claim must cite real event IDs, and every number in the text must be supported by the evidence.
- **Personalizes** the same verified facts: Analyst or Casual fan, in English, Telugu or Hindi.
- **Exports timed overlay JSON** that a graphics system could consume.
- **Shows the proof:** click "Why?" on any claim to see the evidence events plotted on a pitch.

## Architecture

```
sim/simulator.py        synthetic events + planted ground truth (answer files)
        |
analytics/analytics.py  key-moment detection (rolling windows, thresholds, evidence IDs)
        |
agents/story.py         Narrator (template offline, Azure OpenAI optional) -> Verifier
        |
web/render.py           viewer-specific text (mode x language), overlay JSON,
                        number check re-run on the final localized text
        |
web/server.py + index.html   story queue, evidence pitch, momentum timeline, eval panel
eval/run_eval.py        runs 20 matches and prints the accuracy table
```

## How the Verifier works

For each claim it checks that (1) at least one evidence ID is cited, (2) every cited event exists in the match, (3) every cited event belongs to the moment being described, and (4) every number in the text appears in the evidence-derived metrics. A claim that fails any check is blocked and shown with the reason.

## Evaluation (20 synthetic matches)

| Check | Result |
|---|---|
| High press detected | 20/20 |
| Momentum swing detected | 20/20 |
| Big chance detected | 20/20 |
| False positives | 0 |
| Fake claims injected | 128 |
| Fake claims blocked by Verifier | 128 |
| Genuine claims wrongly rejected | 0 |

**Read these numbers honestly:**

- The planted events are strong signals, so 100% detection is an easy test. A harder mode with weaker signals is future work.
- The "hallucinations" are **injected by us** to stress-test the Verifier (half cite a non-existent event ID, half cite a real ID with a wrong number). They are not a measured error rate of any language model.
- The simulator is simple. Scorelines are higher than real football.

## Run it locally (Windows PowerShell)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python sim\simulator.py
python eval\run_eval.py
python web\server.py
```

Open http://localhost:8000. Toggle "Simulate AI hallucination" to see the Verifier block fabricated claims.

With Docker:

```
docker build -t storydesk .
docker run -p 8000:8000 storydesk
```

## Optional: Azure OpenAI narrator

If these environment variables are set, the Narrator calls an Azure OpenAI deployment instead of the offline template (the Verifier still checks everything):

```
AZURE_OAI_ENDPOINT, AZURE_OAI_KEY, AZURE_OAI_DEPLOYMENT, (optional) AZURE_OAI_API_VERSION
```

If the call fails, the pipeline falls back to the template narrator. Never commit keys; `.env` is git-ignored.

## Technologies

- Python standard library (HTTP server), plain HTML/JS front end
- `openai` SDK (`AzureOpenAI` client) for the optional Azure OpenAI path

**Status of the Azure path:** the code is included, but it has **not been tested against a live Azure deployment** because the author did not have an Azure subscription. The demo runs with the offline template narrator.

## AI assistance

This project was built with AI coding assistance (Claude). The author reviewed, ran and tested the code.

## Limitations

- Offline narrator uses fixed templates; Telugu and Hindi text come from templates, not machine translation, and have not been reviewed by a professional translator.
- Detection thresholds are tuned to this simulator.
- Only a few moment types are supported.