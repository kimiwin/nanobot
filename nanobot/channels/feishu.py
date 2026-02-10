"""Feishu (Lark) channel implementation using Long Connection."""

import asyncio
import json

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import FeishuConfig


class FeishuChannel(BaseChannel):
    """
    Feishu (Lark) channel implementation using Long Connection.
    """

    name = "feishu"

    def __init__(self, config: FeishuConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: FeishuConfig = config
        self._client = None
        self._api_client = None

    def _download_file(self, message_id: str, file_key: str, resource_type: str, file_name: str | None = None) -> str | None:
        """Download file from Feishu and return local path."""
        try:
            import lark_oapi as lark
            import os
            import tempfile
        except ImportError:
            return None

        # Ensure download directory exists
        download_dir = os.path.join(tempfile.gettempdir(), "nanobot_downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        # Use file_key if file_name is not provided
        if not file_name:
            file_name = file_key
            # Append extension if possible, but we might not know it
            if resource_type == "image":
                file_name += ".jpg" # Default to jpg for images if unknown
        
        file_path = os.path.join(download_dir, file_name)
        
        try:
            request = lark.im.v1.GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(file_key) \
                .type(resource_type) \
                .build()
                
            response = self._api_client.im.v1.message_resource.get(request)
            
            if not response.success():
                logger.error(f"Failed to download file: {response.code} {response.msg}")
                return None
                
            with open(file_path, "wb") as f:
                f.write(response.file.read())
                
            logger.info(f"Downloaded file to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    def _upload_image(self, file_path: str) -> str | None:
        """Upload image to Feishu and return image_key."""
        try:
            import lark_oapi as lark
            import os
        except ImportError:
            return None
            
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
            
        try:
            with open(file_path, "rb") as f:
                request = lark.im.v1.CreateImageRequest.builder() \
                    .request_body(lark.im.v1.CreateImageRequestBody.builder() \
                        .image_type("message") \
                        .image(f) \
                        .build()) \
                    .build()
                    
                response = self._api_client.im.v1.image.create(request)
                
            if not response.success():
                logger.error(f"Failed to upload image: {response.code} {response.msg}")
                return None
                
            return response.data.image_key
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None

    def _upload_file(self, file_path: str, file_type: str = "stream") -> str | None:
        """Upload file to Feishu and return file_key."""
        try:
            import lark_oapi as lark
            import os
        except ImportError:
            return None
            
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
            
        file_name = os.path.basename(file_path)
        
        try:
            with open(file_path, "rb") as f:
                request = lark.im.v1.CreateFileRequest.builder() \
                    .request_body(lark.im.v1.CreateFileRequestBody.builder() \
                        .file_type(file_type) \
                        .file_name(file_name) \
                        .file(f) \
                        .build()) \
                    .build()
                    
                response = self._api_client.im.v1.file.create(request)
                
            if not response.success():
                logger.error(f"Failed to upload file: {response.code} {response.msg}")
                return None
                
            return response.data.file_key
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None

    async def start(self) -> bool:
        """Start the Feishu client. Returns True on success."""
        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu app_id or app_secret not configured")
            return False

        # Initialize API client for sending messages
        try:
            import lark_oapi as lark
            self._api_client = lark.Client.builder() \
                .app_id(self.config.app_id) \
                .app_secret(self.config.app_secret) \
                .build()
        except ImportError:
            logger.error("lark-oapi package not installed. Please run: pip install lark-oapi")
            return False

        self._running = True
        main_loop = asyncio.get_running_loop()

        # Run the blocking client in a separate thread
        def run_client():
            try:
                # Create a new event loop for this thread
                # This MUST happen before importing lark_oapi because lark_oapi.ws.client
                # captures the current event loop at import time.
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)

                try:
                    import lark_oapi as lark
                except ImportError:
                    logger.error("lark-oapi package not installed. Please run: pip install lark-oapi")
                    self._running = False
                    return

                logger.info("Starting Feishu WebSocket client...")

                def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
                    logger.debug(f"Feishu raw event received: {data}")
                    msg = data.event.message
                    content_str = msg.content
                    
                    text = ""
                    media = []
                    
                    try:
                        content_json = json.loads(content_str)
                        text = content_json.get("text", "")
                        
                        # Handle file/image/media
                        msg_type = msg.message_type
                        file_key = None
                        file_name = None
                        resource_type = None
                        
                        if msg_type == "image":
                            file_key = content_json.get("image_key")
                            resource_type = "image"
                        elif msg_type == "file":
                            file_key = content_json.get("file_key")
                            file_name = content_json.get("file_name")
                            resource_type = "file"
                        elif msg_type == "media": 
                            file_key = content_json.get("file_key")
                            file_name = content_json.get("file_name")
                            resource_type = "media"
                        elif msg_type == "audio":
                            file_key = content_json.get("file_key")
                            resource_type = "file"
                            
                        if file_key and resource_type:
                            file_path = self._download_file(msg.message_id, file_key, resource_type, file_name)
                            if file_path:
                                media.append(file_path)
                                if not text:
                                    text = f"[{msg_type}] {file_name or 'file'}"
                                    
                    except Exception as e:
                        logger.error(f"Error parsing Feishu message content: {e}")
                        text = content_str

                    # Remove bot mention if any
                    if "@_all" in text:
                        text = text.replace("@_all", "").strip()

                    sender_id = data.event.sender.sender_id.open_id
                    chat_id = msg.chat_id

                    logger.info(f"Received Feishu message from {sender_id} in {chat_id}: {text[:50]}...")

                    if self.is_allowed(sender_id):
                        metadata = {
                            "message_id": msg.message_id,
                            "chat_id": chat_id,
                            "msg_type": msg.message_type,
                            "sender_id": sender_id
                        }

                        # Use main_loop to schedule the coroutine in the main thread
                        asyncio.run_coroutine_threadsafe(
                            self._handle_message(
                                sender_id=sender_id,
                                chat_id=chat_id,
                                content=text,
                                metadata=metadata,
                                media=media
                            ),
                            main_loop
                        )
                    else:
                        logger.warning(f"Unauthorized Feishu user: {sender_id}")

                event_handler = (
                    lark.EventDispatcherHandler.builder("", "")
                    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
                    .build()
                )

                # Initialize client inside the thread
                # CRITICAL FIX: lark-oapi.ws.client module captures the event loop at import time.
                # If it was imported in the main thread (which happens in start() for api_client),
                # it holds the main loop. We must monkey-patch it to use our thread's loop.
                import lark_oapi.ws.client
                lark_oapi.ws.client.loop = new_loop
                
                self._client = lark.ws.Client(
                    self.config.app_id,
                    self.config.app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.INFO
                )
                self._client.start()
            except Exception as e:
                if self._running:
                    logger.error(f"Feishu client error: {e}")
                self._running = False

        import threading
        self._thread = threading.Thread(target=run_client, daemon=True)
        self._thread.start()

        return True

    async def stop(self) -> None:
        """Stop the Feishu client."""
        self._running = False
        # lark-oapi ws Client doesn't seem to have an explicit stop() in the sample,
        # but usually these clients have a way to close.
        # If not, the daemon thread will exit when the main process exits.
        logger.info("Feishu channel stopping...")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to Feishu."""
        if not self._api_client:
            logger.warning("Feishu API client not initialized, cannot send message")
            return

        try:
            import lark_oapi as lark
        except ImportError:
            return

        # Use chat_id from metadata or from the message itself
        receive_id = msg.chat_id
        
        # Send text if present
        if msg.content:
            content = json.dumps({"text": msg.content})

            def _send_sync():
                request = lark.im.v1.CreateMessageRequest.builder() \
                    .receive_id_type("chat_id") \
                    .request_body(lark.im.v1.CreateMessageRequestBody.builder() \
                        .receive_id(receive_id) \
                        .msg_type("text") \
                        .content(content) \
                        .build()) \
                    .build()
                return self._api_client.im.v1.message.create(request)

            # Run blocking network call in executor
            loop = asyncio.get_running_loop()
            try:
                response = await loop.run_in_executor(None, _send_sync)
                
                if not response.success():
                    logger.error(f"Failed to send Feishu message: {response.code} {response.msg}")
                else:
                    logger.debug(f"Feishu message sent to {receive_id}")
            except Exception as e:
                logger.error(f"Error sending Feishu message: {e}")

        # Send media if present
        if msg.media:
            for file_path in msg.media:
                try:
                    # Determine msg_type based on extension
                    ext = file_path.lower().split('.')[-1] if '.' in file_path else ""
                    msg_type = "image" if ext in ["jpg", "jpeg", "png", "gif"] else "file"
                    
                    content_dict = {}
                    
                    if msg_type == "image":
                        image_key = await asyncio.to_thread(self._upload_image, file_path)
                        if not image_key:
                            logger.error(f"Failed to upload image for sending: {file_path}")
                            continue
                        content_dict["image_key"] = image_key
                    else:
                        file_key = await asyncio.to_thread(self._upload_file, file_path)
                        if not file_key:
                            logger.error(f"Failed to upload file for sending: {file_path}")
                            continue
                        content_dict["file_key"] = file_key
                        
                    content_json = json.dumps(content_dict)
                    
                    def _send_file_sync(m_type=msg_type, c_json=content_json):
                         request = lark.im.v1.CreateMessageRequest.builder() \
                            .receive_id_type("chat_id") \
                            .request_body(lark.im.v1.CreateMessageRequestBody.builder() \
                                .receive_id(receive_id) \
                                .msg_type(m_type) \
                                .content(c_json) \
                                .build()) \
                            .build()
                         return self._api_client.im.v1.message.create(request)

                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(None, _send_file_sync)
                    
                    if not response.success():
                        logger.error(f"Failed to send Feishu file message: {response.code} {response.msg}")
                    else:
                        logger.debug(f"Feishu file message sent to {receive_id}")
                        
                except Exception as e:
                     logger.error(f"Error sending Feishu file: {e}")
