# Request — Quartz event rename

Quartz now names one of its events differently; here's the updated specification.

## What I need

### Quartz stream, updated (attached)

The text events of `POST {EXTERNAL}/quartz/responses` are now called `output_text`
(previously `text_delta`); their data is unchanged:

```text
event: output_text
data: {"text": "Hi Ola, "}

event: citation
data: {"article_id": "KB-100", "title": "Resetting your password", "url": "https://help.relaydesk.test/north/kb-100"}

event: output_text
data: {"text": "here is how to reset it."}

event: completed
data: {"response_id": "qz-3"}
```

Everything else about the stream (`citation`, `completed`, errors) is unchanged. Some Quartz
servers still send `text_delta` while they switch over; treat the two names the same.

### RelayDesk

- Quartz suggestions work exactly as before with either name: text as it arrives, citations
  kept apart from the text.
- Quartz suggestions saved before this change, and every other service, are unaffected.
