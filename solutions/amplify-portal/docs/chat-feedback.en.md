# Ratings of AI Chat Answers
🌐 **Language / 言語**: [日本語](chat-feedback.md) | English

Users can mark each AI chat answer as good or bad and add a comment. Ratings are stored in DynamoDB, and administrators and auditors can review them day by day. The record has the same shape as the ratings of the permission-aware RAG web app ([FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG)).

## Fields Stored
Ratings are append-only: one rating is one item. Nothing updates or deletes them.

| Field | Content |
|---|---|
| `feedbackId` | UUID |
| `timestamp` / `date` | UTC ISO format / `YYYY-MM-DD` |
| `userId` | The Cognito username passed by the AppSync resolver. A value sent by the browser is not used |
| `responseId` | The ID of the answer (`r-` and 32 hex characters). Checked against `[A-Za-z0-9_-]{1,64}` |
| `rating` | `positive` or `negative` only |
| `comment` | Optional, up to 1,000 characters |
| `modelId` | The model that answered. Characters and length (128) are checked |
| `sourceDocIds` | Opaque IDs of the files the answer drew on (the first 32 hex characters of the key's SHA-256), up to 20 |
| `ttlEpoch` | `timestamp` plus the retention (365 days by default, `FEEDBACK_RETENTION_DAYS`) |

The question (`query`, up to 500 characters) goes into a separate item with the same `feedbackId` (`kind` is `query`), kept for 90 days by default (`FEEDBACK_QUERY_RETENTION_DAYS`). It is text the user typed, so it is kept for less time than the rating. DynamoDB TTL applies per item, which is why it is a separate item.

`sourceDocIds` holds only files that were returned to that user: the `kb_search` results (narrowed to the user's path scope inside the tool) and the keys `read_file` could read within the user's path scope. No ID or name of a file the user could not read is kept. The IDs reach the screen in the chat response and come back with the rating; when a rating arrives only their shape (32 hex characters, up to 20) is checked.

## Who Can Use It
- **Rate**: users who can use the AI chat. An external user who is not allowed AI cannot rate
- **Review**: the `storage-admin` and `auditor` roles. The list does not show the user ID of the person who rated
- **Without the table**: when the Lambda has no `FEEDBACK_TABLE`, the screen shows no rating buttons, and `submitFeedback` does not say it saved anything; it returns `ratings are not enabled`

## How to Review
On the screen: the ratings button in the AI chat header (shown only to storage-admin and auditor) lists the ratings of a day (UTC) with time, rating, question, comment, model and the number of sources.

A weekly pass is intended, in this order:

1. Open each day of the previous week and read the questions and comments of the bad ratings
2. Group similar questions by cause (answered with no source file, had sources but misread them, out of scope, model limit)
3. Decide a fix per cause (add files to the knowledge base, revise the agent's prompt or tools, revise the path scope)
4. The next week, check whether the ratings of the same kind of question changed

Without the screen, query the `ByDate` index by date:

```bash
aws dynamodb query --table-name <name of ChatFeedbackTable> --index-name ByDate \
  --key-condition-expression '#d = :d' --expression-attribute-names '{"#d":"date"}' \
  --expression-attribute-values '{":d":{"S":"2026-11-17"}}'
```

## Permissions
The AgentChat Lambda role gains `dynamodb:PutItem` and `GetItem` on `ChatFeedbackTable` and `dynamodb:Query` on the `ByDate` index. No update or delete permission is given.
