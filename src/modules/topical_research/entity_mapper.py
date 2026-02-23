"""Entity mapping and topical authority analysis using NLP and AI."""

import logging
import math
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy-load spaCy to avoid import cost when not needed
_nlp = None


def _get_nlp():
    """Load the spaCy English model lazily."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model 'en_core_web_sm' loaded successfully")
        except OSError:
            logger.error(
                "spaCy model 'en_core_web_sm' not found. "
                "Install it with: python -m spacy download en_core_web_sm"
            )
            raise
    return _nlp


class EntityMapper:
    """NLP-powered entity extraction, relationship mapping, and topical authority analysis.

    Uses spaCy for named entity recognition and an LLM client for
    semantic similarity, embeddings, and intelligent connection suggestions.

    Usage::

        from src.integrations.llm_client import LLMClient

        mapper = EntityMapper(llm_client=LLMClient())
        entities = mapper.extract_entities("Apple released the new iPhone 15 in Cupertino.")
        graph = await mapper.build_entity_graph("technology", ["smartphones", "AI"])
        authority = await mapper.calculate_topical_authority("example.com", "tech", topical_map)
    """

    def __init__(self, llm_client: Any = None) -> None:
        """Initialize the EntityMapper.

        Args:
            llm_client: An instance of LLMClient for AI-powered analysis.
                        If None, a default instance will be created.
        """
        self.llm_client = llm_client

        if self.llm_client is None:
            try:
                from src.integrations.llm_client import LLMClient
                self.llm_client = LLMClient()
                logger.info("Created default LLMClient for EntityMapper")
            except Exception as exc:
                logger.warning("Could not create default LLMClient: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_entities(
        self,
        text: str,
    ) -> list[dict[str, Any]]:
        """Extract named entities from text using spaCy NLP.

        Performs NER (Named Entity Recognition) on the input text and
        returns entities with their type, frequency, and a relevance
        score based on positional and frequency heuristics.

        Args:
            text: The text to extract entities from.

        Returns:
            List of dicts with keys: entity, entity_type, frequency,
            relevance_score, positions.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to extract_entities")
            return []

        nlp = _get_nlp()
        doc = nlp(text)

        # Count entity occurrences and track positions
        entity_counts: Counter = Counter()
        entity_types: dict[str, str] = {}
        entity_positions: dict[str, list[int]] = {}

        for ent in doc.ents:
            normalized = ent.text.strip()
            if not normalized or len(normalized) < 2:
                continue
            entity_counts[normalized] += 1
            entity_types[normalized] = ent.label_
            if normalized not in entity_positions:
                entity_positions[normalized] = []
            entity_positions[normalized].append(ent.start_char)

        if not entity_counts:
            logger.info("No entities found in text (len=%d)", len(text))
            return []

        # Calculate relevance scores
        max_freq = max(entity_counts.values()) if entity_counts else 1
        text_length = max(len(text), 1)
        results: list[dict[str, Any]] = []

        for entity_text, freq in entity_counts.most_common():
            # Position score: entities appearing earlier are more relevant
            first_pos = entity_positions[entity_text][0]
            position_score = 1.0 - (first_pos / text_length)
            position_score = max(0.0, min(1.0, position_score))

            # Frequency score normalized to 0-1
            freq_score = freq / max_freq

            # Type bonus: certain entity types are more SEO-relevant
            type_weights = {
                "ORG": 1.2,
                "PRODUCT": 1.3,
                "PERSON": 1.0,
                "GPE": 1.1,
                "LOC": 1.1,
                "WORK_OF_ART": 0.9,
                "EVENT": 1.0,
                "FAC": 0.8,
                "NORP": 0.7,
                "LAW": 0.8,
                "LANGUAGE": 0.6,
                "DATE": 0.4,
                "TIME": 0.3,
                "MONEY": 0.7,
                "QUANTITY": 0.4,
                "ORDINAL": 0.3,
                "CARDINAL": 0.3,
                "PERCENT": 0.5,
            }
            ent_type = entity_types.get(entity_text, "UNKNOWN")
            type_weight = type_weights.get(ent_type, 0.5)

            # Combined relevance score (0-100)
            raw_score = (
                (freq_score * 0.4)
                + (position_score * 0.3)
                + (type_weight / 1.3 * 0.3)
            )
            relevance_score = round(min(raw_score * 100, 100), 1)

            results.append({
                "entity": entity_text,
                "entity_type": ent_type,
                "frequency": freq,
                "relevance_score": relevance_score,
                "positions": entity_positions[entity_text],
            })

        # Sort by relevance descending
        results.sort(key=lambda e: e["relevance_score"], reverse=True)

        logger.info(
            "Extracted %d unique entities from text (len=%d)",
            len(results), len(text),
        )
        return results

    async def build_entity_graph(
        self,
        niche: str,
        topics: list[str],
    ) -> dict[str, Any]:
        """Build an entity relationship graph for topics in a niche.

        Creates a graph structure showing how topics semantically connect
        to each other, with edge weights representing relationship strength.

        Args:
            niche: The niche context for relationship analysis.
            topics: List of topic strings to map relationships between.

        Returns:
            Dict with 'nodes' (list of topic node dicts) and
            'edges' (list of relationship edge dicts).
        """
        logger.info(
            "Building entity graph for niche %r with %d topics",
            niche, len(topics),
        )

        if not topics:
            return {"nodes": [], "edges": [], "niche": niche}

        # Build nodes
        nodes: list[dict[str, Any]] = []
        for i, topic in enumerate(topics):
            nodes.append({
                "id": i,
                "label": topic,
                "type": "topic",
            })

        # Use LLM to determine relationships
        edges: list[dict[str, Any]] = []

        if self.llm_client and len(topics) > 1:
            try:
                import json
                topics_json = json.dumps(topics[:30])
                prompt = (
                    'Analyze the semantic relationships between these topics '
                    'in the "' + niche + '" niche:\n'
                    + topics_json
                    + '\n\nFor each meaningful pair of related topics, provide:'
                    + '\n- source: index of first topic (0-based)'
                    + '\n- target: index of second topic (0-based)'
                    + '\n- weight: relationship strength 0.1 to 1.0'
                    + '\n- relationship: type of relationship '
                    + '(parent-child|sibling|prerequisite|related|complementary)'
                    + '\n- description: brief description of the connection'
                    + '\n\nOnly include pairs with genuine topical relevance. '
                    + 'Return JSON array:'
                    + '\n[{"source": 0, "target": 1, "weight": 0.8, '
                    + '"relationship": "sibling", '
                    + '"description": "Both cover..."}]'
                )
                edge_data = await self.llm_client.generate_json(
                    prompt=prompt,
                    system_prompt=(
                        "You are a semantic analysis expert. "
                        "Identify meaningful topical relationships. "
                        "Respond ONLY with valid JSON."
                    ),
                    max_tokens=2000,
                    temperature=0.3,
                )
                if isinstance(edge_data, list):
                    for edge in edge_data:
                        src = edge.get("source", -1)
                        tgt = edge.get("target", -1)
                        if (
                            isinstance(src, int)
                            and isinstance(tgt, int)
                            and 0 <= src < len(topics)
                            and 0 <= tgt < len(topics)
                            and src != tgt
                        ):
                            edges.append({
                                "source": src,
                                "target": tgt,
                                "source_label": topics[src],
                                "target_label": topics[tgt],
                                "weight": min(
                                    float(edge.get("weight", 0.5)), 1.0
                                ),
                                "relationship": edge.get(
                                    "relationship", "related"
                                ),
                                "description": edge.get("description", ""),
                            })
                logger.info(
                    "Entity graph built: %d nodes, %d edges",
                    len(nodes), len(edges),
                )
            except Exception as exc:
                logger.error("Failed to build entity graph via LLM: %s", exc)

        # Compute node metrics
        for node in nodes:
            node_id = node["id"]
            connected_edges = [
                e for e in edges
                if e["source"] == node_id or e["target"] == node_id
            ]
            node["degree"] = len(connected_edges)
            if connected_edges:
                node["avg_weight"] = round(
                    sum(e["weight"] for e in connected_edges)
                    / len(connected_edges),
                    3,
                )
            else:
                node["avg_weight"] = 0.0

        return {
            "niche": niche,
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    async def calculate_topical_authority(
        self,
        domain: str,
        niche: str,
        topical_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Estimate topical authority coverage for a domain.

        Compares a domain's content coverage against an ideal topical
        map to calculate authority scores and identify missing topics.

        Args:
            domain: The target domain to evaluate (e.g. "example.com").
            niche: The niche for context.
            topical_map: A topical map dict with pillars/clusters/articles.

        Returns:
            Dict with authority_score, coverage_percentage, covered_topics,
            missing_topics, and recommendations.
        """
        logger.info(
            "Calculating topical authority for %r in niche %r",
            domain, niche,
        )

        # Extract all topics from the topical map
        all_topics: list[str] = []
        pillar_topics: list[str] = []
        cluster_topics: list[str] = []
        article_topics: list[str] = []

        for pillar in topical_map.get("pillars", []):
            p_title = pillar.get("title", "")
            if p_title:
                all_topics.append(p_title)
                pillar_topics.append(p_title)
            for cluster in pillar.get("clusters", []):
                c_title = cluster.get("title", "")
                if c_title:
                    all_topics.append(c_title)
                    cluster_topics.append(c_title)
                for article in cluster.get("supporting_articles", []):
                    a_title = article.get("title", "")
                    if a_title:
                        all_topics.append(a_title)
                        article_topics.append(a_title)

        total_topics = len(all_topics)
        if total_topics == 0:
            logger.warning("No topics found in topical map")
            return {
                "domain": domain,
                "niche": niche,
                "authority_score": 0.0,
                "coverage_percentage": 0.0,
                "covered_topics": [],
                "missing_topics": [],
                "recommendations": [],
                "error": "No topics found in topical map",
            }

        # Use AI to estimate which topics the domain likely covers
        covered_topics: list[str] = []
        missing_topics: list[str] = []

        try:
            import json
            topics_json = json.dumps(all_topics[:50])
            prompt = (
                'For the domain "' + domain + '" operating in the "'
                + niche + '" niche, estimate which of these topics the '
                + 'domain likely covers based on the domain name and niche:'
                + '\n\nTopics:\n' + topics_json
                + '\n\nReturn JSON with two arrays:'
                + '\n{'
                + '\n  "likely_covered": ["topics the domain probably covers"],'
                + '\n  "likely_missing": ["topics the domain probably lacks"],'
                + '\n  "coverage_confidence": "low|medium|high",'
                + '\n  "reasoning": "brief explanation"'
                + '\n}'
                + '\n\nNote: Without crawling the actual site, provide your '
                + 'best estimate. A generic domain likely covers fewer topics. '
                + 'A niche-specific domain likely covers more.'
            )
            coverage = await self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=(
                    "You are an SEO topical authority analyst. "
                    "Estimate content coverage based on domain context. "
                    "Respond ONLY with valid JSON."
                ),
                max_tokens=2000,
                temperature=0.3,
            )
            if isinstance(coverage, dict):
                covered_topics = coverage.get("likely_covered", [])
                missing_topics = coverage.get("likely_missing", [])
                confidence = coverage.get("coverage_confidence", "low")
                reasoning = coverage.get("reasoning", "")
            else:
                confidence = "low"
                reasoning = "Could not parse coverage estimate"
        except Exception as exc:
            logger.error("Failed to estimate topical coverage: %s", exc)
            confidence = "low"
            reasoning = "AI analysis failed: " + str(exc)
            # Fallback: assume 20% coverage
            split_point = max(1, total_topics // 5)
            covered_topics = all_topics[:split_point]
            missing_topics = all_topics[split_point:]

        # Calculate authority score
        num_covered = len(covered_topics)
        coverage_pct = round((num_covered / total_topics) * 100, 1) if total_topics > 0 else 0.0

        # Weighted authority score (pillars worth more)
        pillar_covered = len(
            [t for t in covered_topics if t in pillar_topics]
        )
        cluster_covered = len(
            [t for t in covered_topics if t in cluster_topics]
        )
        article_covered = len(
            [t for t in covered_topics if t in article_topics]
        )

        pillar_total = max(len(pillar_topics), 1)
        cluster_total = max(len(cluster_topics), 1)
        article_total = max(len(article_topics), 1)

        weighted_score = (
            (pillar_covered / pillar_total) * 0.4
            + (cluster_covered / cluster_total) * 0.35
            + (article_covered / article_total) * 0.25
        )
        authority_score = round(weighted_score * 100, 1)

        # Generate priority recommendations
        recommendations: list[dict[str, str]] = []
        missing_pillars = [t for t in missing_topics if t in pillar_topics]
        missing_clusters = [t for t in missing_topics if t in cluster_topics]

        for mp in missing_pillars[:3]:
            recommendations.append({
                "action": "Create pillar content for: " + mp,
                "priority": "high",
                "impact": "Major authority boost - pillar topic coverage",
            })

        for mc in missing_clusters[:5]:
            recommendations.append({
                "action": "Create cluster content for: " + mc,
                "priority": "medium",
                "impact": "Significant authority improvement in sub-topic",
            })

        result = {
            "domain": domain,
            "niche": niche,
            "authority_score": authority_score,
            "coverage_percentage": coverage_pct,
            "total_topics_in_map": total_topics,
            "covered_count": num_covered,
            "missing_count": len(missing_topics),
            "covered_topics": covered_topics,
            "missing_topics": missing_topics,
            "pillar_coverage": round(
                (pillar_covered / pillar_total) * 100, 1
            ),
            "cluster_coverage": round(
                (cluster_covered / cluster_total) * 100, 1
            ),
            "article_coverage": round(
                (article_covered / article_total) * 100, 1
            ),
            "coverage_confidence": confidence,
            "reasoning": reasoning,
            "recommendations": recommendations,
        }

        logger.info(
            "Topical authority for %r: score=%.1f, coverage=%.1f%%",
            domain, authority_score, coverage_pct,
        )
        return result

    async def suggest_semantic_connections(
        self,
        topics: list[str],
    ) -> list[dict[str, Any]]:
        """Find semantic relationships between topics for internal linking.

        Uses NLP and optional embeddings to discover which topics are
        semantically related and should link to each other.

        Args:
            topics: List of topic/article title strings.

        Returns:
            List of connection dicts with source, target, similarity_score,
            and suggested_anchor_text.
        """
        logger.info(
            "Suggesting semantic connections for %d topics", len(topics)
        )

        if len(topics) < 2:
            return []

        connections: list[dict[str, Any]] = []

        # Strategy 1: Try embeddings for similarity if available
        embeddings_available = False
        similarity_matrix: list[list[float]] = []

        if self.llm_client:
            try:
                embeddings = await self.llm_client.generate_embeddings(
                    texts=topics[:50]
                )
                if embeddings and len(embeddings) == len(topics[:50]):
                    embeddings_available = True
                    # Calculate cosine similarity matrix
                    num = len(embeddings)
                    similarity_matrix = [
                        [0.0] * num for _ in range(num)
                    ]
                    for i in range(num):
                        for j in range(i + 1, num):
                            sim = self._cosine_similarity(
                                embeddings[i], embeddings[j]
                            )
                            similarity_matrix[i][j] = sim
                            similarity_matrix[j][i] = sim

                    logger.info(
                        "Computed embedding similarity for %d topics", num
                    )
            except Exception as exc:
                logger.warning(
                    "Embeddings not available, falling back to NLP: %s", exc
                )

        if embeddings_available:
            # Use embedding similarity to find connections
            num_topics = len(topics[:50])
            for i in range(num_topics):
                # Find top 3 most similar topics for each
                similarities = []
                for j in range(num_topics):
                    if i != j:
                        similarities.append(
                            (j, similarity_matrix[i][j])
                        )
                similarities.sort(key=lambda x: x[1], reverse=True)

                for j, sim in similarities[:3]:
                    if sim >= 0.5:  # Only include meaningful connections
                        connections.append({
                            "source": topics[i],
                            "target": topics[j],
                            "similarity_score": round(sim, 3),
                            "method": "embedding_similarity",
                            "suggested_anchor_text": "",
                        })
        else:
            # Strategy 2: Use NLP word overlap + AI
            nlp = _get_nlp()
            topic_tokens: list[set[str]] = []
            for topic in topics[:50]:
                doc = nlp(topic.lower())
                tokens = set()
                for token in doc:
                    if not token.is_stop and not token.is_punct and len(token.text) > 2:
                        tokens.add(token.lemma_)
                topic_tokens.append(tokens)

            num_topics = len(topic_tokens)
            for i in range(num_topics):
                for j in range(i + 1, num_topics):
                    if not topic_tokens[i] or not topic_tokens[j]:
                        continue
                    intersection = topic_tokens[i] & topic_tokens[j]
                    union = topic_tokens[i] | topic_tokens[j]
                    if union:
                        jaccard = len(intersection) / len(union)
                    else:
                        jaccard = 0.0
                    if jaccard >= 0.15:
                        connections.append({
                            "source": topics[i],
                            "target": topics[j],
                            "similarity_score": round(jaccard, 3),
                            "method": "token_overlap",
                            "shared_terms": list(intersection),
                            "suggested_anchor_text": "",
                        })

        # Enrich top connections with anchor text suggestions via AI
        if connections and self.llm_client:
            top_connections = sorted(
                connections,
                key=lambda c: c["similarity_score"],
                reverse=True,
            )[:20]

            try:
                import json
                pairs = []
                for conn in top_connections:
                    pairs.append({
                        "source": conn["source"],
                        "target": conn["target"],
                    })
                prompt = (
                    'For these pairs of related content topics, suggest '
                    + 'natural anchor text that could be used to link from '
                    + 'the source article to the target article:\n'
                    + json.dumps(pairs, indent=2)
                    + '\n\nReturn JSON array with suggested anchor text:'
                    + '\n[{"source": "...", "target": "...", '
                    + '"anchor_text": "natural linking phrase"}]'
                )
                anchors = await self.llm_client.generate_json(
                    prompt=prompt,
                    system_prompt=(
                        "You are an SEO internal linking specialist. "
                        "Suggest natural, contextual anchor text phrases. "
                        "Respond ONLY with valid JSON."
                    ),
                    max_tokens=1500,
                    temperature=0.3,
                )
                if isinstance(anchors, list):
                    anchor_map = {}
                    for a in anchors:
                        key = a.get("source", "") + "||" + a.get("target", "")
                        anchor_map[key] = a.get("anchor_text", "")

                    for conn in connections:
                        key = conn["source"] + "||" + conn["target"]
                        if key in anchor_map:
                            conn["suggested_anchor_text"] = anchor_map[key]

                logger.info(
                    "Enriched %d connections with anchor text",
                    len(top_connections),
                )
            except Exception as exc:
                logger.error(
                    "Failed to generate anchor text suggestions: %s", exc
                )

        # Sort by similarity descending
        connections.sort(
            key=lambda c: c["similarity_score"], reverse=True
        )

        # Remove near-duplicate reverse pairs
        seen_pairs: set[tuple[str, str]] = set()
        unique_connections: list[dict[str, Any]] = []
        for conn in connections:
            pair = (conn["source"], conn["target"])
            reverse_pair = (conn["target"], conn["source"])
            if pair not in seen_pairs and reverse_pair not in seen_pairs:
                seen_pairs.add(pair)
                unique_connections.append(conn)

        logger.info(
            "Semantic connections found: %d unique connections",
            len(unique_connections),
        )
        return unique_connections

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(
        vec_a: list[float],
        vec_b: list[float],
    ) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)
