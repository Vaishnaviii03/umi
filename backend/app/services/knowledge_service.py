from typing import Optional
from dataclasses import dataclass
from app.services.boss_profile import get_boss_profile, BossProfile
from app.services.greeting_service import get_greeting_service, GreetingService
from app.db.repositories import retrieve_relevant_memories
from app.db.session import get_db
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger("umi.knowledge")


@dataclass
class KnowledgeContext:
    """Structured context for LLM consumption."""
    profile_summary: str
    greeting: Optional[str] = None
    relevant_memories: list[str] = None
    active_projects: list[str] = None
    goals_summary: str = None

    def __post_init__(self):
        if self.relevant_memories is None:
            self.relevant_memories = []
        if self.active_projects is None:
            self.active_projects = []
        if self.goals_summary is None:
            self.goals_summary = ""


class KnowledgeService:
    def __init__(
        self,
        profile: Optional[BossProfile] = None,
        greeting_service: Optional[GreetingService] = None,
    ):
        self.profile = profile or get_boss_profile()
        self.greeting_service = greeting_service or get_greeting_service()

    def get_greeting(
        self,
        context: str = "startup",
        hour: Optional[int] = None,
    ) -> str:
        """Get a time-aware greeting."""
        return self.greeting_service.get_full_greeting(context=context, hour=hour)

    def get_profile_summary(self, detail: str = "normal") -> str:
        """Get the boss profile summary."""
        return self.profile.generate_profile_summary(detail=detail)

    def get_comprehensive_profile(self) -> str:
        """Get comprehensive profile for 'tell me everything' requests."""
        parts = [self.profile.generate_profile_summary(detail="detailed")]

        # Add goals
        parts.append("\n**Goals:**")
        parts.append(self.profile.get_all_goals_text())

        # Add active projects
        active = self.profile.get_active_projects()
        if active:
            parts.append("\n**Active Projects:**")
            for p in active:
                parts.append(f"- **{p.name}**: {p.description} — *Goal: {p.goal}*")

        # Add technical interests
        parts.append("\n**Technical Interests:**")
        for t in self.profile.technical_interests:
            parts.append(f"- {t.name}: {t.level.replace('_', ' ')}")

        # Add hobbies
        parts.append(f"\n**Hobbies:** {', '.join(self.profile.hobbies)}")

        # Add ideal routine
        parts.append("\n**Ideal Routine:**")
        for i, item in enumerate(self.profile.ideal_routine, 1):
            parts.append(f"{i}. {item}")

        # Add work style
        parts.append("\n**Work Style:**")
        for trait in self.profile.personality_traits:
            parts.append(f"- {trait}")
        parts.append(f"- Distractions: {self.profile.distractions[0]}")

        # Add Tony Stark note
        parts.append(f"\n**Inspiration:** {self.profile.tony_stark_note}")

        return "\n".join(parts)

    def retrieve_memories(self, query: str, db: Session, limit: int = 5) -> list[str]:
        """Retrieve relevant memories from the database."""
        try:
            memories = retrieve_relevant_memories(db, query, limit=limit)
            return [m.content for m in memories]
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")
            return []

    def build_context(
        self,
        user_message: str,
        db: Session,
        include_greeting: bool = False,
        greeting_context: str = "text_chat",
        include_memories: bool = True,
    ) -> KnowledgeContext:
        """Build structured knowledge context for LLM."""
        # Check if this is a profile query
        is_profile_query = self._is_profile_query(user_message)
        is_detailed = self._is_detailed_query(user_message)

        # Get profile summary
        if is_profile_query:
            if is_detailed:
                profile_text = self.get_comprehensive_profile()
            else:
                profile_text = self.get_profile_summary(detail="normal")
        else:
            profile_text = self.get_profile_summary(detail="concise")

        # Get greeting if requested
        greeting = None
        if include_greeting:
            greeting = self.get_greeting(context=greeting_context)

        # Retrieve relevant memories (layering: some fast/voice paths skip them)
        memories = []
        if include_memories:
            memories = self.retrieve_memories(user_message, db, limit=4)

        # Active projects
        active_projects = [f"{p.name}: {p.description}" for p in self.profile.get_active_projects()]

        # Goals summary
        goals_summary = self.profile.get_all_goals_text()

        return KnowledgeContext(
            profile_summary=profile_text,
            greeting=greeting,
            relevant_memories=memories,
            active_projects=active_projects,
            goals_summary=goals_summary,
        )

    def _is_profile_query(self, message: str) -> bool:
        """Check if the user is asking about their profile."""
        profile_triggers = [
            "do you know about me",
            "what do you know about me",
            "tell me about myself",
            "who am i",
            "what do you remember about me",
            "what do you know about me",
            "who is my boss",
            "tell me about me",
            "tell me everything",
            "tell me all",
            "everything you know",
            "all you know",
        ]
        msg_lower = message.lower().strip()
        return any(trigger in msg_lower for trigger in profile_triggers)

    def _is_detailed_query(self, message: str) -> bool:
        """Check if the user wants detailed information."""
        detailed_triggers = [
            "everything",
            "all",
            "comprehensive",
            "detailed",
            "full",
            "complete",
        ]
        msg_lower = message.lower()
        return any(trigger in msg_lower for trigger in detailed_triggers)

    def format_context_for_llm(self, context: KnowledgeContext) -> str:
        """Format knowledge context for LLM system prompt."""
        parts = []

        if context.greeting:
            parts.append(f"[Greeting: {context.greeting}]")

        parts.append(f"[Boss Profile]\n{context.profile_summary}")

        if context.active_projects:
            parts.append(f"[Active Projects]\n" + "\n".join(f"- {p}" for p in context.active_projects))

        if context.goals_summary:
            parts.append(f"[Goals]\n{context.goals_summary}")

        if context.relevant_memories:
            mem_text = "\n".join(f"- {m}" for m in context.relevant_memories)
            parts.append(f"[Relevant Memories]\n{mem_text}")

        return "\n\n".join(parts)


# Global instance
_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service