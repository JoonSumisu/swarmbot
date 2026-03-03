    async def _run_message_loop(self):
        logger.info("Gateway is ready. Listening for messages...")
        
        try:
            while not self._stop_event.is_set():
                # Wait for message
                message: InboundMessage = await self.bus.recv()
                
                if not message:
                    continue
                    
                logger.info(f"Received message from {message.source}: {message.content[:50]}...")
                
                # Launch async handler
                asyncio.create_task(self._handle_message_async(message))
                
        except asyncio.CancelledError:
            logger.info("Message loop cancelled.")
        finally:
            self.stop()

    async def _handle_message_async(self, message: InboundMessage):
        """Async wrapper for blocking inference."""
        loop = asyncio.get_running_loop()
        try:
            # Run blocking inference in thread pool
            response_text = await loop.run_in_executor(
                self._executor, 
                self.inference_loop.run, 
                message.content,
                message.chat_id or "unknown"
            )
            
            # Send reply (back on async loop)
            reply = OutboundMessage(
                content=response_text,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                source="swarmbot"
            )
            await self.bus.send(reply)
            
        except Exception as e:
            logger.error(f"Inference processing failed: {e}")
