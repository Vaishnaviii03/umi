from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import pytz


@dataclass
class Project:
    name: str
    description: str
    goal: str
    active: bool = True


@dataclass
class Goal:
    title: str
    description: str
    category: str  # startup, ai, building, personal_development


@dataclass
class TechnicalInterest:
    name: str
    level: str = "passionate_about_learning"  # learning, building_with, mastered
    description: str = ""


@dataclass
class BossProfile:
    # Identity
    name: str = "Neerish Pandey"
    preferred_address: str = "Boss"
    location: str = "Uttar Pradesh, India"
    age: int = 16
    education: str = "Class 10 student"
    gender: str = "male"
    roles: list[str] = field(default_factory=lambda: [
        "Founder", "Builder", "Learner", "Creator", "Tech enthusiast"
    ])

    # Projects
    projects: list[Project] = field(default_factory=lambda: [
        Project(
            name="Founder OS",
            description="Personal startup focused on building tools for founders",
            goal="Grow to a meaningful level with real revenue and profit",
        ),
        Project(
            name="Umi",
            description="Personal AI female assistant",
            goal="Build a highly capable personal AI assistant with strong personal relationship and useful capabilities",
        ),
    ])

    # Technical Interests
    technical_interests: list[TechnicalInterest] = field(default_factory=lambda: [
        TechnicalInterest("Artificial Intelligence", description="Core interest, combining with other fields"),
        TechnicalInterest("Machine Learning", description="Building and training models"),
        TechnicalInterest("Electronics", description="Hardware and circuit design"),
        TechnicalInterest("Robotics", description="Combining AI with physical systems"),
        TechnicalInterest("Programming", description="Software development across domains"),
        TechnicalInterest("Computer Vision", description="AI + visual perception"),
        TechnicalInterest("Hardware", description="Physical computing and embedded systems"),
    ])

    # Goals
    goals: list[Goal] = field(default_factory=lambda: [
        Goal(
            title="Grow Founder OS",
            description="Grow the startup to a meaningful level with real revenue and profit",
            category="startup"
        ),
        Goal(
            title="Master AI and technical skills",
            description="Develop deep expertise in AI and related technical fields",
            category="ai"
        ),
        Goal(
            title="Build impressive projects",
            description="Create awesome, ambitious, impressive technology projects",
            category="building"
        ),
        Goal(
            title="Develop inventor/builder mindset",
            description="Develop an inventor/builder mindset inspired by Tony Stark's qualities",
            category="personal_development"
        ),
    ])

    # Personality
    personality_traits: list[str] = field(default_factory=lambda: [
        "ambitious", "curious", "experimental", "proactive",
        "fast-moving", "highly persistent", "passionate about technology",
        "highly interested in building things"
    ])

    # Distractions
    distractions: list[str] = field(default_factory=lambda: [
        "Notifications and incoming messages from friends, family, and important people"
    ])

    # Hobbies
    hobbies: list[str] = field(default_factory=lambda: [
        "cricket", "sketching", "traveling", "exploring", "eating/trying food"
    ])

    # Communication
    communication_style: str = "casual, warm, friendly, slightly playful, respectful, natural"
    preferred_name: str = "Boss"

    # Ideal routine
    ideal_routine: list[str] = field(default_factory=lambda: [
        "Wake around 5 AM",
        "Get ready",
        "Exercise",
        "Gym",
        "Breakfast",
        "Work on startup / office work",
        "Work on personal projects",
        "Travel/explore",
        "Eat and relax",
        "Continue project work",
        "Hobbies",
        "Sleep",
    ])

    # Tony Stark inspiration note
    tony_stark_note: str = (
        "Boss admires Tony Stark's inventor, engineer, builder, and ambitious "
        "problem-solving mindset. He wants to develop similar technical creativity "
        "and ambitious project-building ability. This is inspiration/reference, "
        "not a literal personality template."
    )

    def generate_profile_summary(self, detail: str = "normal") -> str:
        """Generate a natural language profile summary from structured data."""
        parts = []

        # Core identity
        parts.append(
            f"I'm {self.name}, a {self.age}-year-old {self.education} from {self.location}. "
            f"I'm a {', '.join(self.roles[:-1])}, and {self.roles[-1]} with a strong passion for technology."
        )

        # Technical interests
        interest_names = [t.name for t in self.technical_interests]
        parts.append(
            f"I'm especially interested in {', '.join(interest_names[:-1])}, and {interest_names[-1]}. "
            f"I love learning by building things rather than just studying theory."
        )

        # Current projects
        if detail in ("normal", "detailed"):
            project_descriptions = []
            for p in self.projects:
                if p.active:
                    project_descriptions.append(f"{p.name} ({p.goal})")
            if project_descriptions:
                parts.append(
                    f"Right now, I'm working on {', '.join(project_descriptions[:-1])}, "
                    f"and {project_descriptions[-1]}."
                )

        # Personality
        if detail in ("normal", "detailed"):
            traits = ", ".join(self.personality_traits[:-1]) + f", and {self.personality_traits[-1]}"
            parts.append(f"I'm {traits}.")

        # Tony Stark inspiration
        if detail in ("normal", "detailed"):
            parts.append(
                f"I admire the inventor and builder mindset associated with Tony Stark "
                f"and want to develop that kind of creative engineering mindset myself."
            )

        # Hobbies
        if detail in ("normal", "detailed"):
            hobby_list = ", ".join(self.hobbies[:-1]) + f", and {self.hobbies[-1]}"
            parts.append(f"Outside technology, I enjoy {hobby_list}.")

        # Communication preference
        parts.append(
            f"I want you to be {self.communication_style} — with me as your {self.preferred_name}."
        )

        return " ".join(parts)

    def get_active_projects(self) -> list[Project]:
        return [p for p in self.projects if p.active]

    def get_goals_by_category(self, category: str) -> list[Goal]:
        return [g for g in self.goals if g.category == category]

    def get_all_goals_text(self) -> str:
        by_cat = {}
        for g in self.goals:
            by_cat.setdefault(g.category, []).append(g)
        parts = []
        for cat, goals in by_cat.items():
            parts.append(f"**{cat.title()}**: " + "; ".join(g.description for g in goals))
        return "\n".join(parts)


# Singleton instance
_boss_profile: Optional[BossProfile] = None


def get_boss_profile() -> BossProfile:
    global _boss_profile
    if _boss_profile is None:
        _boss_profile = BossProfile()
    return _boss_profile