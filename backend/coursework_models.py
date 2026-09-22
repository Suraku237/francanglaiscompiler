from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from .schemas import RequestModel

GrammarText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
PracticeText = Annotated[str, StringConstraints(max_length=4000)]


class ProjectProfile(RequestModel):
    group_members: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = Field(
        min_length=3, max_length=3
    )
    grammar: GrammarText
    manual_transcription_confirmed: bool = False
    grammar_rationale: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6000)] = ""
    discussion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=12000)] = ""
    collection_method: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6000)] = ""
    limitations: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6000)] = ""

    @field_validator("group_members")
    @classmethod
    def distinct_members(cls, members: list[str]) -> list[str]:
        names = [name.casefold() for name in members if name]
        if len(names) != len(set(names)):
            raise ValueError("Each group member must have a distinct name.")
        return members


class GrammarRequest(RequestModel):
    grammar: GrammarText


class ParseRequest(GrammarRequest):
    text: PracticeText = ""


class ScreenshotRequest(RequestModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    data_url: Annotated[str, StringConstraints(max_length=2800000)]
