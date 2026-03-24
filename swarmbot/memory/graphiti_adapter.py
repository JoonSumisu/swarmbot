from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..config_manager import ProviderConfig, WORKSPACE_PATH, load_config
from ..llm_client import OpenAICompatibleClient


def create_nomic_embedder(model: str = "nomic-embed-text-v1.5", device: str = "auto"):
    """Factory function to create a nomic embedder"""
    from graphiti_core.embedder.client import EmbedderClient
    from typing import Iterable
    
    class NomicEmbedder(EmbedderClient):
        def __init__(self, model: str, device: str):
            self.model = model
            self.device = device
            self._nomic_embed = None
        
        def _get_nomic(self):
            if self._nomic_embed is None:
                from nomic import embed as nomic_embed
                self._nomic_embed = nomic_embed
            return self._nomic_embed
        
        async def embed(self, texts: List[str]) -> List[List[float]]:
            nomic = self._get_nomic()
            output = nomic.text(
                texts=texts,
                model=self.model,
                task_type="search_document",
                inference_mode="local",
                device=self.device,
            )
            return output["embeddings"]
        
        async def create(self, input_data) -> list[float]:
            if isinstance(input_data, str):
                input_data = [input_data]
            results = await self.embed(input_data)
            return results[0] if len(results) == 1 else results
        
        async def create_batch(self, input_data_list) -> list[list[float]]:
            return await self.embed(input_data_list)
    
    return NomicEmbedder(model, device)


class GraphitiMemoryAdapter:
    def __init__(
        self,
        provider_config: Optional[ProviderConfig] = None,
        db_path: Optional[str] = None,
    ):
        self.provider_config = provider_config or load_config().providers[0]
        self.db_path = db_path or os.path.join(WORKSPACE_PATH, "graphiti.kuzu")
        self._graphiti = None
        self._llm_client = None
        self._nomic_embedder = None

    def _detect_embedding_device(self) -> str:
        import os
        os.environ["GPT4ALL_NO_GPU"] = "1"
        
        device = self.provider_config.embedding_device
        if device:
            return device
        
        try:
            from gpt4all import GPT4All
            GPT4All("test", n_threads=1, device="cpu")
            return "cpu"
        except:
            return "cpu"

    async def initialize(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        from graphiti_core import Graphiti
        from graphiti_core.driver.kuzu_driver import KuzuDriver
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.llm_client.config import LLMConfig

        embedding_model = "nomic-embed-text-v1.5"
        embedding_device = self._detect_embedding_device()
        
        self._nomic_embedder = create_nomic_embedder(
            model=embedding_model,
            device=embedding_device,
        )
        print(f"[Graphiti] Using embedding model: {embedding_model}, device: {embedding_device}")

        llm_config = LLMConfig(
            api_key=self.provider_config.api_key or "dummy",
            model=self.provider_config.model,
            small_model=self.provider_config.model,
            base_url=self.provider_config.base_url or None,
        )

        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        
        self._llm_client = OpenAIGenericClient(config=llm_config)
        
        original_generate = self._llm_client._generate_response
        
        async def patched_generate(messages, response_model=None, max_tokens=2000, model_size=None):
            try:
                result = await original_generate(messages, response_model, max_tokens, model_size)
                
                if isinstance(result, dict):
                    has_entities = "extracted_entities" in result
                    has_edges = "edges" in result
                    
                    if not has_entities or not has_edges:
                        result = await handle_reasoning_model(messages)
                    
                    result = convert_to_graphiti_format(result)
                    
                    if not result.get("extracted_entities"):
                        result["extracted_entities"] = []
                    if not result.get("edges"):
                        result["edges"] = []
                else:
                    result = await handle_reasoning_model(messages)
                
                return result
            except Exception as e:
                try:
                    result = await handle_reasoning_model(messages)
                    return convert_to_graphiti_format(result)
                except:
                    return {"extracted_entities": [], "edges": [], "error": str(e)}
        
        async def handle_reasoning_model(messages):
            from openai import AsyncOpenAI
            client = AsyncOpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
            
            prompt = ""
            for m in messages:
                prompt += f"{m.role}: {m.content}\n"
            
            prompt += "\n\nRespond with ONLY valid JSON, NO markdown, NO code blocks, NO explanations. Just the JSON."
            
            resp = await client.chat.completions.create(
                model=llm_config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1,
            )
            msg = resp.choices[0].message
            content = msg.content or ""
            reasoning = getattr(msg, 'reasoning_content', None) or ""
            
            combined = (content + reasoning).strip() if content else (reasoning + content).strip()
            
            combined = combined.strip()
            combined = combined.strip('```json')
            combined = combined.strip('```')
            combined = combined.strip()
            
            json_match = re.search(r'\{.*\}', combined, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            
            if combined.startswith('{'):
                try:
                    return json.loads(combined)
                except:
                    pass
            
            return {"extracted_entities": [], "edges": []}
        
        def convert_to_graphiti_format(result):
            if not isinstance(result, dict):
                return {"extracted_entities": [], "edges": []}
            
            formatted = {}
            
            if "extracted_entities" in result:
                formatted["extracted_entities"] = result["extracted_entities"]
            elif "entities" in result:
                entities = []
                for ent in result.get("entities", []):
                    name = ent.get("text") or ent.get("name") or ent.get("entity", "")
                    if name:
                        entities.append({"name": name, "entity_type_id": 1})
                formatted["extracted_entities"] = entities
            else:
                formatted["extracted_entities"] = []
            
            if "edges" in result:
                formatted["edges"] = result["edges"]
            elif "relations" in result:
                edges = []
                for rel in result.get("relations", []):
                    source = rel.get("source") or rel.get("source_entity") or rel.get("from", "")
                    target = rel.get("target") or rel.get("target_entity") or rel.get("to", "")
                    rel_type = rel.get("type") or rel.get("relation_type") or "RELATES_TO"
                    fact = rel.get("fact") or rel.get("description") or ""
                    if source and target:
                        edges.append({
                            "source_entity_name": source,
                            "target_entity_name": target,
                            "relation_type": rel_type.upper() if isinstance(rel_type, str) else "RELATES_TO",
                            "fact": fact
                        })
                formatted["edges"] = edges
            else:
                formatted["edges"] = []
            
            return formatted
        
        self._llm_client._generate_response = patched_generate

        kuzu_driver = KuzuDriver(db=self.db_path)

        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.llm_client.config import LLMConfig as CrossEncoderConfig

        cross_encoder_config = CrossEncoderConfig(
            api_key="dummy",
            model=self.provider_config.model,
            small_model=self.provider_config.model,
            base_url=self.provider_config.base_url or None,
        )
        cross_encoder = OpenAIRerankerClient(config=cross_encoder_config)

        self._graphiti = Graphiti(
            graph_driver=kuzu_driver,
            llm_client=self._llm_client,
            embedder=self._nomic_embedder,
            cross_encoder=cross_encoder,
        )

        try:
            await self._graphiti.build_indices_and_constraints()
        except Exception as e:
            print(f"[Graphiti] build_indices_and_constraints: {e}")

        await self._create_fts_index()

    async def _create_fts_index(self) -> None:
        try:
            await self._graphiti.driver.execute_query(
                "CALL CREATE_FTS_INDEX('Entity', 'node_name_and_summary', ['name','summary'])"
            )
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                pass
            else:
                print(f"[Graphiti] FTS index creation: {e}")

    def embed_text(self, texts: List[str], task_type: str = "search_document") -> List[List[float]]:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
        except RuntimeError:
            pass
        
        return asyncio.run(self._nomic_embedder.embed(texts))

    async def add_episode(
        self,
        content: str,
        entities: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from datetime import datetime, timezone
        from graphiti_core.nodes import EpisodeType
        
        try:
            episode = await self._graphiti.add_episode(
                name=f"episode_{int(datetime.now().timestamp())}",
                episode_body=content,
                source_description=metadata.get("source", "swarmbot") if metadata else "swarmbot",
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.message,
            )
            
            if hasattr(episode, 'episodes') and episode.episodes:
                ep_id = str(episode.episodes[0].uuid)
            elif hasattr(episode, 'uuid'):
                ep_id = str(episode.uuid)
            else:
                ep_id = str(datetime.now().timestamp())
            
            return {"ok": True, "episode_id": ep_id}
        except Exception as e:
            print(f"[Graphiti] add_episode error: {e}")
            return {"ok": False, "error": str(e)}

    async def search(
        self,
        query: str,
        limit: int = 5,
        time_range: Optional[Dict[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            results = await self._graphiti.search(
                query=query,
                num_results=limit,
            )

            return [
                {
                    "uuid": str(r.uuid),
                    "content": r.node_content,
                    "name": r.name,
                    "summary": r.summary,
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Graphiti] Search error: {e}")
            return []

    async def get_nodes_by_episode(
        self,
        episode_uuid: str,
    ) -> List[Dict[str, Any]]:
        """获取 episode 关联的节点"""
        try:
            results = await self._graphiti.get_nodes_and_edges_by_episode(episode_uuid=episode_uuid)
            return [
                {
                    "name": r.name,
                    "summary": r.summary,
                    "type": type(r).__name__,
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Graphiti] get_nodes_by_episode error: {e}")
            return []

    async def get_entity_history(
        self,
        entity_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取实体历史 - 通过查询实现"""
        try:
            cypher = f"""
            MATCH (e:Entity {{name: '{entity_name}'}})<-[:MENTIONS]-(r)
            RETURN e.name as name, e.summary as summary
            LIMIT {limit}
            """
            results = await self._graphiti.driver.execute_query(cypher)
            return [
                {
                    "name": r.get("name", ""),
                    "summary": r.get("summary", ""),
                }
                for r in results
            ]
        except Exception as e:
            return []

    async def batch_add(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        for item in items:
            await self.add_episode(
                content=item.get("content", ""),
                entities=item.get("entities"),
                metadata=item.get("metadata"),
            )
        return {"ok": True, "count": len(items)}

    async def search_bm25(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """BM25 全文搜索 (通过 Graphiti search)"""
        try:
            results = await self._graphiti.search(query, num_results=limit)
            return [
                {
                    "name": r.name,
                    "summary": r.summary,
                    "content": r.node_content,
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Graphiti] BM25 search error: {e}")
            return []

    async def search_hybrid(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """混合搜索 (Vector + BM25)"""
        return await self.search(query, limit)

    async def search_hybrid(
        self,
        query: str,
        limit: int = 5,
        time_range: Optional[Dict[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        """混合搜索：Vector + BM25 + Graph Traversal"""
        return await self.search(query, limit, time_range)

    async def get_related_entities(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取实体的关联实体 (Graph Traversal)"""
        try:
            history = await self.get_entity_history(entity_name, limit)
            
            cypher = f"""
            MATCH (e:Entity {{name: '{entity_name}'}})-[r:MENTIONS]->(related:Entity)
            RETURN related.name as name, related.summary as summary, 
                   type(r) as relation, r.weight as weight
            LIMIT {limit}
            """
            results = await self._graphiti.driver.execute_query(cypher)
            
            related = [
                {
                    "name": r.get("name", ""),
                    "summary": r.get("summary", ""),
                    "relation": r.get("relation", ""),
                }
                for r in results
            ]
            
            if not related and history:
                related = [
                    {
                        "name": h.get("name", ""),
                        "summary": h.get("summary", ""),
                        "relation": "historical_mention",
                    }
                    for h in history[:limit]
                ]
            
            return related
        except Exception as e:
            print(f"[Graphiti] Graph traversal error: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            try:
                entity_result = loop.run_until_complete(
                    self._graphiti.driver.execute_query("MATCH (e:Entity) RETURN count(e) as count")
                )
                entity_count = entity_result[0].get("count", 0) if entity_result else 0
            except:
                entity_count = 0
            
            try:
                episode_result = loop.run_until_complete(
                    self._graphiti.driver.execute_query("MATCH (e:Episode) RETURN count(e) as count")
                )
                episode_count = episode_result[0].get("count", 0) if episode_result else 0
            except:
                episode_count = 0
            
            try:
                edge_result = loop.run_until_complete(
                    self._graphiti.driver.execute_query("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
                )
                edge_count = edge_result[0].get("count", 0) if edge_result else 0
            except:
                edge_count = 0
            
            return {
                "entities": entity_count,
                "episodes": episode_count,
                "relations": edge_count,
            }
        except Exception as e:
            print(f"[Graphiti] Stats error: {e}")
            return {"entities": 0, "episodes": 0, "relations": 0}

    async def close(self) -> None:
        if self._graphiti:
            await self._graphiti.close()
