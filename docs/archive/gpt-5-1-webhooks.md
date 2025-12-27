Webhook Events
Webhooks are HTTP requests sent by OpenAI to a URL you specify when certain events happen during the course of API usage.

Learn more about webhooks.

response.completed
Sent when a background response has been completed.

created_at
integer

The Unix timestamp (in seconds) of when the model response was completed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always response.completed.

OBJECT response.completed
{
  "id": "evt_abc123",
  "type": "response.completed",
  "created_at": 1719168000,
  "data": {
    "id": "resp_abc123"
  }
}
response.cancelled
Sent when a background response has been cancelled.

created_at
integer

The Unix timestamp (in seconds) of when the model response was cancelled.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always response.cancelled.

OBJECT response.cancelled
{
  "id": "evt_abc123",
  "type": "response.cancelled",
  "created_at": 1719168000,
  "data": {
    "id": "resp_abc123"
  }
}
response.failed
Sent when a background response has failed.

created_at
integer

The Unix timestamp (in seconds) of when the model response failed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always response.failed.

OBJECT response.failed
{
  "id": "evt_abc123",
  "type": "response.failed",
  "created_at": 1719168000,
  "data": {
    "id": "resp_abc123"
  }
}
response.incomplete
Sent when a background response has been interrupted.

created_at
integer

The Unix timestamp (in seconds) of when the model response was interrupted.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always response.incomplete.

OBJECT response.incomplete
{
  "id": "evt_abc123",
  "type": "response.incomplete",
  "created_at": 1719168000,
  "data": {
    "id": "resp_abc123"
  }
}
batch.completed
Sent when a batch API request has been completed.

created_at
integer

The Unix timestamp (in seconds) of when the batch API request was completed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always batch.completed.

OBJECT batch.completed
{
  "id": "evt_abc123",
  "type": "batch.completed",
  "created_at": 1719168000,
  "data": {
    "id": "batch_abc123"
  }
}
batch.cancelled
Sent when a batch API request has been cancelled.

created_at
integer

The Unix timestamp (in seconds) of when the batch API request was cancelled.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always batch.cancelled.

OBJECT batch.cancelled
{
  "id": "evt_abc123",
  "type": "batch.cancelled",
  "created_at": 1719168000,
  "data": {
    "id": "batch_abc123"
  }
}
batch.expired
Sent when a batch API request has expired.

created_at
integer

The Unix timestamp (in seconds) of when the batch API request expired.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always batch.expired.

OBJECT batch.expired
{
  "id": "evt_abc123",
  "type": "batch.expired",
  "created_at": 1719168000,
  "data": {
    "id": "batch_abc123"
  }
}
batch.failed
Sent when a batch API request has failed.

created_at
integer

The Unix timestamp (in seconds) of when the batch API request failed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always batch.failed.

OBJECT batch.failed
{
  "id": "evt_abc123",
  "type": "batch.failed",
  "created_at": 1719168000,
  "data": {
    "id": "batch_abc123"
  }
}
fine_tuning.job.succeeded
Sent when a fine-tuning job has succeeded.

created_at
integer

The Unix timestamp (in seconds) of when the fine-tuning job succeeded.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always fine_tuning.job.succeeded.

OBJECT fine_tuning.job.succeeded
{
  "id": "evt_abc123",
  "type": "fine_tuning.job.succeeded",
  "created_at": 1719168000,
  "data": {
    "id": "ftjob_abc123"
  }
}
fine_tuning.job.failed
Sent when a fine-tuning job has failed.

created_at
integer

The Unix timestamp (in seconds) of when the fine-tuning job failed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always fine_tuning.job.failed.

OBJECT fine_tuning.job.failed
{
  "id": "evt_abc123",
  "type": "fine_tuning.job.failed",
  "created_at": 1719168000,
  "data": {
    "id": "ftjob_abc123"
  }
}
fine_tuning.job.cancelled
Sent when a fine-tuning job has been cancelled.

created_at
integer

The Unix timestamp (in seconds) of when the fine-tuning job was cancelled.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always fine_tuning.job.cancelled.

OBJECT fine_tuning.job.cancelled
{
  "id": "evt_abc123",
  "type": "fine_tuning.job.cancelled",
  "created_at": 1719168000,
  "data": {
    "id": "ftjob_abc123"
  }
}
eval.run.succeeded
Sent when an eval run has succeeded.

created_at
integer

The Unix timestamp (in seconds) of when the eval run succeeded.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always eval.run.succeeded.

OBJECT eval.run.succeeded
{
  "id": "evt_abc123",
  "type": "eval.run.succeeded",
  "created_at": 1719168000,
  "data": {
    "id": "evalrun_abc123"
  }
}
eval.run.failed
Sent when an eval run has failed.

created_at
integer

The Unix timestamp (in seconds) of when the eval run failed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always eval.run.failed.

OBJECT eval.run.failed
{
  "id": "evt_abc123",
  "type": "eval.run.failed",
  "created_at": 1719168000,
  "data": {
    "id": "evalrun_abc123"
  }
}
eval.run.canceled
Sent when an eval run has been canceled.

created_at
integer

The Unix timestamp (in seconds) of when the eval run was canceled.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always eval.run.canceled.

OBJECT eval.run.canceled
{
  "id": "evt_abc123",
  "type": "eval.run.canceled",
  "created_at": 1719168000,
  "data": {
    "id": "evalrun_abc123"
  }
}
realtime.call.incoming
Sent when Realtime API Receives a incoming SIP call.

created_at
integer

The Unix timestamp (in seconds) of when the model response was completed.

data
object

Event data payload.


Show properties
id
string

The unique ID of the event.

object
string

The object of the event. Always event.

type
string

The type of the event. Always realtime.call.incoming.

OBJECT realtime.call.incoming
{
  "id": "evt_abc123",
  "type": "realtime.call.incoming",
  "created_at": 1719168000,
  "data": {
    "call_id": "rtc_479a275623b54bdb9b6fbae2f7cbd408",
    "sip_headers": [
      {"name": "Max-Forwards", "value": "63"},
      {"name": "CSeq", "value": "851287 INVITE"},
      {"name": "Content-Type", "value": "application/sdp"},
    ]
  }
}