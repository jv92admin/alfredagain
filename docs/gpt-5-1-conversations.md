Create a conversation
post
 
https://api.openai.com/v1/conversations
Create a conversation.

Request body
items
array

Optional
Initial items to include in the conversation context. You may add up to 20 items at a time.


Show possible types
metadata
object or null

Optional
Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional information about the object in a structured format, and querying for objects via API or the dashboard. Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.

Returns
Returns a Conversation object.

Example request
curl https://api.openai.com/v1/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "metadata": {"topic": "demo"},
    "items": [
      {
        "type": "message",
        "role": "user",
        "content": "Hello!"
      }
    ]
  }'
Response
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
Retrieve a conversation
get
 
https://api.openai.com/v1/conversations/{conversation_id}
Get a conversation

Path parameters
conversation_id
string

Required
The ID of the conversation to retrieve.

Returns
Returns a Conversation object.

Example request
curl https://api.openai.com/v1/conversations/conv_123 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
Response
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
Update a conversation
post
 
https://api.openai.com/v1/conversations/{conversation_id}
Update a conversation

Path parameters
conversation_id
string

Required
The ID of the conversation to update.

Request body
metadata
map

Required
Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional information about the object in a structured format, and querying for objects via API or the dashboard.

Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.

Returns
Returns the updated Conversation object.

Example request
curl https://api.openai.com/v1/conversations/conv_123 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "metadata": {"topic": "project-x"}
  }'
Response
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "project-x"}
}
Delete a conversation
delete
 
https://api.openai.com/v1/conversations/{conversation_id}
Delete a conversation. Items in the conversation will not be deleted.

Path parameters
conversation_id
string

Required
The ID of the conversation to delete.

Returns
A success message.

Example request
curl -X DELETE https://api.openai.com/v1/conversations/conv_123 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
Response
{
  "id": "conv_123",
  "object": "conversation.deleted",
  "deleted": true
}
List items
get
 
https://api.openai.com/v1/conversations/{conversation_id}/items
List all items for a conversation with the given ID.

Path parameters
conversation_id
string

Required
The ID of the conversation to list items for.

Query parameters
after
string

Optional
An item ID to list items after, used in pagination.

include
array

Optional
Specify additional output data to include in the model response. Currently supported values are:

web_search_call.action.sources: Include the sources of the web search tool call.
code_interpreter_call.outputs: Includes the outputs of python code execution in code interpreter tool call items.
computer_call_output.output.image_url: Include image urls from the computer call output.
file_search_call.results: Include the search results of the file search tool call.
message.input_image.image_url: Include image urls from the input message.
message.output_text.logprobs: Include logprobs with assistant messages.
reasoning.encrypted_content: Includes an encrypted version of reasoning tokens in reasoning item outputs. This enables reasoning items to be used in multi-turn conversations when using the Responses API statelessly (like when the store parameter is set to false, or when an organization is enrolled in the zero data retention program).
limit
integer

Optional
Defaults to 20
A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.

order
string

Optional
The order to return the input items in. Default is desc.

asc: Return the input items in ascending order.
desc: Return the input items in descending order.
Returns
Returns a list object containing Conversation items.

Example request
curl "https://api.openai.com/v1/conversations/conv_123/items?limit=10" \
  -H "Authorization: Bearer $OPENAI_API_KEY"
Response
{
  "object": "list",
  "data": [
    {
      "type": "message",
      "id": "msg_abc",
      "status": "completed",
      "role": "user",
      "content": [
        {"type": "input_text", "text": "Hello!"}
      ]
    }
  ],
  "first_id": "msg_abc",
  "last_id": "msg_abc",
  "has_more": false
}
Create items
post
 
https://api.openai.com/v1/conversations/{conversation_id}/items
Create items in a conversation with the given ID.

Path parameters
conversation_id
string

Required
The ID of the conversation to add the item to.

Query parameters
include
array

Optional
Additional fields to include in the response. See the include parameter for listing Conversation items above for more information.

Request body
items
array

Required
The items to add to the conversation. You may add up to 20 items at a time.


Show possible types
Returns
Returns the list of added items.

Example request
curl https://api.openai.com/v1/conversations/conv_123/items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "items": [
      {
        "type": "message",
        "role": "user",
        "content": [
          {"type": "input_text", "text": "Hello!"}
        ]
      },
      {
        "type": "message",
        "role": "user",
        "content": [
          {"type": "input_text", "text": "How are you?"}
        ]
      }
    ]
  }'
Response
{
  "object": "list",
  "data": [
    {
      "type": "message",
      "id": "msg_abc",
      "status": "completed",
      "role": "user",
      "content": [
        {"type": "input_text", "text": "Hello!"}
      ]
    },
    {
      "type": "message",
      "id": "msg_def",
      "status": "completed",
      "role": "user",
      "content": [
        {"type": "input_text", "text": "How are you?"}
      ]
    }
  ],
  "first_id": "msg_abc",
  "last_id": "msg_def",
  "has_more": false
}
Retrieve an item
get
 
https://api.openai.com/v1/conversations/{conversation_id}/items/{item_id}
Get a single item from a conversation with the given IDs.

Path parameters
conversation_id
string

Required
The ID of the conversation that contains the item.

item_id
string

Required
The ID of the item to retrieve.

Query parameters
include
array

Optional
Additional fields to include in the response. See the include parameter for listing Conversation items above for more information.

Returns
Returns a Conversation Item.

Example request
curl https://api.openai.com/v1/conversations/conv_123/items/msg_abc \
  -H "Authorization: Bearer $OPENAI_API_KEY"
Response
{
  "type": "message",
  "id": "msg_abc",
  "status": "completed",
  "role": "user",
  "content": [
    {"type": "input_text", "text": "Hello!"}
  ]
}
Delete an item
delete
 
https://api.openai.com/v1/conversations/{conversation_id}/items/{item_id}
Delete an item from a conversation with the given IDs.

Path parameters
conversation_id
string

Required
The ID of the conversation that contains the item.

item_id
string

Required
The ID of the item to delete.

Returns
Returns the updated Conversation object.

Example request
curl -X DELETE https://api.openai.com/v1/conversations/conv_123/items/msg_abc \
  -H "Authorization: Bearer $OPENAI_API_KEY"
Response
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
The conversation object
created_at
integer

The time at which the conversation was created, measured in seconds since the Unix epoch.

id
string

The unique ID of the conversation.

metadata
Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional information about the object in a structured format, and querying for objects via API or the dashboard. Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.

object
string

The object type, which is always conversation.

The item list
A list of Conversation items.

data
array

A list of conversation items.


Show possible types
first_id
string

The ID of the first item in the list.

has_more
boolean

Whether there are more items available.

last_id
string

The ID of the last item in the list.

object
string

The type of object returned, must be list.