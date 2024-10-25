import asyncio
import json
import websockets

from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Any, Callable, Coroutine, Dict, List
from langchain_openai_voice.utils import amerge
from langchain_openai_voice.agent_state import AgentState

from langchain_core.tools import BaseTool
from langchain_core._api import beta
from langchain_core.utils import secret_from_env

from pydantic import BaseModel, Field, SecretStr, PrivateAttr

DEFAULT_MODEL = "gpt-4o-realtime-preview-2024-10-01"
DEFAULT_URL = "wss://api.openai.com/v1/realtime"

EVENTS_TO_IGNORE = {
    "response.function_call_arguments.delta",
    "response.audio_transcript.delta",
    "response.created",
    "response.content_part.added",
    "response.content_part.done",
    "session.created",
    "session.updated",
    "response.audio_transcript.done",
    "response.audio_transcript.delta",

}


@asynccontextmanager
async def connect(*, api_key: str, model: str, url: str) -> AsyncGenerator[
    tuple[
        Callable[[dict[str, Any] | str], Coroutine[Any, Any, None]],
        AsyncIterator[dict[str, Any]],
    ],
    None,
]:
    """
    async with connect(model="gpt-4o-realtime-preview-2024-10-01") as websocket:
        await websocket.send("Hello, world!")
        async for message in websocket:
            print(message)
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    url = url or DEFAULT_URL
    url += f"?model={model}"

    websocket = await websockets.connect(url, extra_headers=headers)

    try:

        async def send_event(event: dict[str, Any] | str) -> None:
            formatted_event = json.dumps(event) if isinstance(event, dict) else event
            await websocket.send(formatted_event)

        async def event_stream() -> AsyncIterator[dict[str, Any]]:
            async for raw_event in websocket:
                yield json.loads(raw_event)

        stream: AsyncIterator[dict[str, Any]] = event_stream()

        yield send_event, stream
    finally:
        await websocket.close()


class VoiceToolExecutor(BaseModel):
    """
    Can accept function calls and emits function call outputs to a stream.
    """

    tools_by_name: dict[str, BaseTool]
    _trigger_future: asyncio.Future = PrivateAttr(default_factory=asyncio.Future)
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    state: AgentState = Field(
        default_factory=lambda: AgentState(
            message="",
            tool_calls=[],
            cart_data=[],
            next="",
            desired_quantity_error_list=[],
            item_missing_in_cart_list=[],
            item_missing_in_store_list=[],
            unit_of_measure_miss_match=[],
            reduce_quantity_error_list=[],
            grocery_item_looking_for_found_list=[],
            grocery_item_looking_for_not_found_list=[],
            similar_items_to_items_looking_for_in_store={"desired_items": [], "similar_items": []}

        )
    )


    def update_state_with_result(self, function_name: str, tool_output: Dict[str, Any]):
        """
        Updates the AgentState based on the tool's output.
        """
        if function_name == "add_modify_grocery_item_to_cart":
            (
                products_not_found_in_store,
                product_not_found_in_cart,
                unit_miss_match,
                desired_quantity_error,
                quantity_reduce_error,
                similar_items_in_store,
                cart_dict,
            ) = tool_output

            if cart_dict:
                self.state["cart_data"] = self.update_cart_data(self.state["cart_data"], cart_dict)

            if products_not_found_in_store:
                self.state["item_missing_in_store_list"].append(products_not_found_in_store)
            if product_not_found_in_cart:
                self.state["item_missing_in_cart_list"].append(product_not_found_in_cart)
            if unit_miss_match:
                self.state["unit_of_measure_miss_match"].append(unit_miss_match)
            if desired_quantity_error:
                self.state["desired_quantity_error_list"].append(desired_quantity_error)
            if quantity_reduce_error:
                self.state["reduce_quantity_error_list"].append(quantity_reduce_error)
            if similar_items_in_store:
                self.state["similar_items_to_items_looking_for_in_store"]["desired_items"].extend(similar_items_in_store)

        elif function_name == "remove_item_from_cart":
            u_cart, removed_item_error = tool_output
            if removed_item_error:
                self.state["item_missing_in_cart_list"].append(removed_item_error)
            self.state["cart_data"] = u_cart

        elif function_name == "grocery_item_info":
            product_not_found, product_found = tool_output
            if product_found:
                self.state["grocery_item_looking_for_found_list"].append(product_found)
            else:
                self.state["grocery_item_looking_for_not_found_list"].append(product_not_found)


    def update_cart_data(self, cart_data: List[Dict[str, Any]], cart_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Updates the cart data with the new or modified item.
        """
        item_exists = False
        for idx, item in enumerate(cart_data):
            if item["item_name"].lower() == cart_dict["item_name"].lower():
                cart_data[idx] = cart_dict
                item_exists = True
                break
        if not item_exists:
            cart_data.append(cart_dict)
        return cart_data


    def prepare_state_summary(self) -> str:
        summaries = []
        if self.state["desired_quantity_error_list"]:
            summaries.append(f"Desired quantity errors: {self.state['desired_quantity_error_list']}")
        if self.state["item_missing_in_cart_list"]:
            summaries.append(f"Items missing in cart: {self.state['item_missing_in_cart_list']}")
        if self.state["item_missing_in_store_list"]:
            summaries.append(f"Items missing in store: {self.state['item_missing_in_store_list']}")
        if self.state["unit_of_measure_miss_match"]:
            summaries.append(f"Unit of measure mismatches: {self.state['unit_of_measure_miss_match']}")
        if self.state["reduce_quantity_error_list"]:
            summaries.append(f"Reduce quantity errors: {self.state['reduce_quantity_error_list']}")
        if self.state["grocery_item_looking_for_found_list"]:
            summaries.append(f"Items found: {self.state['grocery_item_looking_for_found_list']}")
        if self.state["grocery_item_looking_for_not_found_list"]:
            summaries.append(f"Items not found: {self.state['grocery_item_looking_for_not_found_list']}")
        if self.state["similar_items_to_items_looking_for_in_store"]:
            summaries.append(f"Similar items in store: {self.state['similar_items_to_items_looking_for_in_store']}")

        return "\n".join(summaries) if summaries else ""



    async def _trigger_func(self) -> dict:  # returns a tool call
        return await self._trigger_future

    async def add_tool_call(self, tool_call: dict) -> None:
        # lock to avoid simultaneous tool calls racing and missing
        # _trigger_future being
        async with self._lock:
            if self._trigger_future.done():
                # TODO: handle simultaneous tool calls better
                raise ValueError("Tool call adding already in progress")

            self._trigger_future.set_result(tool_call)

    async def _create_tool_call_task(self, tool_call: dict) -> asyncio.Task[dict]:
        tool = self.tools_by_name.get(tool_call["name"])
        if tool is None:
            # immediately yield error, do not add task
            raise ValueError(
                f"tool {tool_call['name']} not found. "
                f"Must be one of {list(self.tools_by_name.keys())}"
            )

        # try to parse args
        try:
            args = json.loads(tool_call["arguments"])
            
            # Add 'grocery_cart' to args if the tool requires it
            if tool_call["name"] in ["add_modify_grocery_item_to_cart", "remove_item_from_cart", 'complete_cart_details']:
                args["grocery_cart"] = self.state['cart_data']

        except json.JSONDecodeError:
            raise ValueError(
                f"failed to parse arguments `{tool_call['arguments']}`. Must be valid JSON."
            )

        async def run_tool() -> dict:
            result = await tool.ainvoke(args)

            print(result)
            
            try:
                result_str = json.dumps(result)

            except TypeError:
                # not json serializable, use str
                result_str = str(result)

            self.update_state_with_result(tool_call["name"], result)
            state_summary = self.prepare_state_summary()


            if tool_call['name'] in ["complete_cart_details", "save_grocery_order", "check_tracking_status", "submit_complaint"]:
                response_content = {
                    "tool_output": result,
                }

            elif tool_call['name'] in ["instaworld_tracking_tool", "retriever_instaworld_txt", "tavily_tool"]:
                response_content = {
                    "tool_output": result,
                }
            
            elif tool_call['name'] == "generate_promotional_message" and result is not None:
                response_content = {
                    "promotional_message_to_be_sent": result,
                }
            
            elif result is None:
                response_content = {
                    "tool_output": "Promo message is already sent!",
                }
            
            else:
                response_content = {
                    "tool_output": result,
                    "state_summary": state_summary
                }

            result_str = json.dumps(response_content)

            # print("\n********************** CART DATA **************************")
            # print(self.state)
            # print("************************************************************\n")

            return {
                "type": "conversation.item.create",
                "item": {
                    "id": tool_call["call_id"],
                    "call_id": tool_call["call_id"],
                    "type": "function_call_output",
                    "output": result_str,
                },
            }

        task = asyncio.create_task(run_tool())
        return task



    async def output_iterator(self) -> AsyncIterator[dict]:  # yield events
        trigger_task = asyncio.create_task(self._trigger_func())
        tasks = set([trigger_task])
        while True:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                tasks.remove(task)
                if task == trigger_task:
                    async with self._lock:
                        self._trigger_future = asyncio.Future()
                    trigger_task = asyncio.create_task(self._trigger_func())
                    tasks.add(trigger_task)
                    tool_call = task.result()
                    try:
                        new_task = await self._create_tool_call_task(tool_call)
                        tasks.add(new_task)
                    except ValueError as e:
                        yield {
                            "type": "conversation.item.create",
                            "item": {
                                "id": tool_call["call_id"],
                                "call_id": tool_call["call_id"],
                                "type": "function_call_output",
                                "output": (f"Error: {str(e)}"),
                            },
                        }
                else:
                    yield task.result()


@beta()
class OpenAIVoiceReactAgent(BaseModel):
    model: str
    api_key: SecretStr = Field(
        alias="openai_api_key",
        default_factory=secret_from_env("OPENAI_API_KEY", default=""),
    )
    instructions: str | None = None
    tools: list[BaseTool] | None = None
    url: str = Field(default=DEFAULT_URL)

    async def aconnect(
        self,
        input_stream: AsyncIterator[str],
        send_output_chunk: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Connect to the OpenAI API and send and receive messages.

        input_stream: AsyncIterator[str]
            Stream of input events to send to the model. Usually transports input_audio_buffer.append events from the microphone.
        output: Callable[[str], None]
            Callback to receive output events from the model. Usually sends response.audio.delta events to the speaker.

        """
        # formatted_tools: list[BaseTool] = [
        #     tool if isinstance(tool, BaseTool) else tool_converter.wr(tool)  # type: ignore
        #     for tool in self.tools or []
        # ]
        tools_by_name = {tool.name: tool for tool in self.tools}
        tool_executor = VoiceToolExecutor(tools_by_name=tools_by_name)
        ids = []

        async with connect(
            model=self.model, api_key=self.api_key.get_secret_value(), url=self.url
        ) as (
            model_send,
            model_receive_stream,
        ):
            # sent tools and instructions with initial chunk
            audio_id = None
            content_id = None

            tool_defs = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": tool.args},
                }
                for tool in tools_by_name.values()
            ]
            await model_send(
                {
                    "type": "session.update",
                    "session": {
                        "instructions": self.instructions,
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500
                    },
                        "input_audio_transcription": {
                            "model": "whisper-1",
                        },
                        "input_audio_format": "g711_ulaw",
                        "output_audio_format": "g711_ulaw",
                        "tools": tool_defs,
                    },
                }
            )
            async for stream_key, data_raw in amerge(
                input_mic=input_stream,
                output_speaker=model_receive_stream,
                tool_outputs=tool_executor.output_iterator(),
            ):
                try:
                    data = (
                        json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                    )
                except json.JSONDecodeError:
                    print("error decoding data:", data_raw)
                    continue

                if stream_key == "input_mic":
                    await model_send(data)

                elif stream_key == "tool_outputs":
                    print("tool output", data)
                    await model_send(data)
                    await model_send({"type": "response.create", "response": {}})
                    

                    print("\n********************** CART DATA **************************")
                    print(tool_executor.state)
                    print("************************************************************\n")




                elif stream_key == "output_speaker":

                    t = data["type"]
                    if t == "response.audio.delta":
                        await send_output_chunk(json.dumps(data))
                        # audio_id = data["item_id"]
                        # content_id = data["content_index"]


                    elif t == "input_audio_buffer.speech_started":
                        print("interrupt\n")
                        await send_output_chunk(json.dumps(data))

                        # if audio_id is not None:
                        #     await model_send({
                        #         "event_id": "event_678",
                        #         "type": "conversation.item.truncate",
                        #         "item_id": audio_id,
                        #         "content_index": content_id,
                        #         "audio_end_ms": data["audio_start_ms"]
                        #     })
                        # send_output_chunk(json.dumps(data))

                
                    elif t == "error":
                        print("error:", data)
                    
                    elif t == "conversation.item.created":
                        if 'item' in data:
                            li = data['item']
                            if 'content' in li and li['content']:
                                for part in li['content']:
                                    if 'type' in part and part['type'] in ['audio', 'input_audio']:
                                        if 'id' in data['item']:
                                            ids.append(data['item']['id'])
                                            print(f"A new item created with ID: {data['item']['id']}\n")

                        # li = data['item']
                        
                        # if li['content']:
                        #     for part in li['content']:
                        #         if part['type'] in ['audio', 'input_audio']:
                        #             ids.append(data["item"]["id"])
                        #             print(f"A new item created with ID: {data['item']['id']}\n")


                        while len(ids) > 4:
                            x = ids.pop(0)
                            await model_send({"event_id": "event_901", "type": "conversation.item.delete", "item_id": x})


                    elif t == "response.function_call_arguments.done":
                        print("tool call", data)
                        await tool_executor.add_tool_call(data)

                    elif t == "response.audio_transcript.done":
                        print("model:", data["transcript"])
                        # await send_output_chunk(json.dumps(data))

                    
                    # elif t == "response.audio_transcript.delta":
                        # await send_output_chunk(json.dumps(data))

                    elif t == "response.audio.done":
                        x = data["item_id"]
                        await model_send({"event_id": "event_901", "type": "conversation.item.delete", "item_id": x})


                    elif t == "conversation.item.input_audio_transcription.completed":
                        print("user:", data["transcript"])
                        # await send_output_chunk(json.dumps(data))

                    elif t == "response.done":
                        usage = data["response"]["usage"]
                        print("\n******************  USAGE COST ******************\n")
                        print(usage)
                        print("*************************************************\n")

                        # await send_output_chunk(json.dumps({'type': 'tool_output', 'data': tool_executor.state['cart_data']}))

                        # await model_send({"event_id": "event_007", "type": "input_audio_buffer.clear"})


                    # elif t == "response.output_item.done":
                    #     print("\nRESPONSE INTERUPPTED !!!\n")
 
                    # elif t == "response.audio.done":
                    #     print("\nAudio Interrupted!")
                        # await send_output_chunk(json.dumps(data))
                        

                    elif t in EVENTS_TO_IGNORE:
                        pass
                    else:
                        print(t)


__all__ = ["OpenAIVoiceReactAgent"]
