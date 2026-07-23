from enum import Enum
from pathlib import Path

class PageType(Enum):
    CATEGORY="category"
    THEORY="theory"
    MCQ="mcq"
    SUBJECTIVE="subjective"
    END="end"

class LearningBackend:
    def __init__(self, course_path=None):
        project_path = Path(__file__).resolve().parent
        self.course_path = project_path / "course" if course_path is None else Path(course_path)
        self.score=0
        self.events=[]
        self.answered_step_ids=set()
        self.steps=[
            {"type":PageType.THEORY,"title":"Introduction","content":"Welcome to the chapter. Read before continuing."},
            {"type":PageType.MCQ,"question":"2 + 5 = ?","options":["5","6","7","8"],"answer":2,"explanation":"2+5=7","time_limit":30},
            {"type":PageType.SUBJECTIVE,"question":"Explain why prime numbers are useful.","time_limit":60},
            {"type":PageType.MCQ,"question":"Square root of 81?","options":["7","8","9","10"],"answer":2,"explanation":"9×9=81","time_limit":30},
        ]

    def get_categories(self):
        """Return visible subject folders from the configured course directory."""
        if not self.course_path.is_dir():
            return []
        return sorted(
            folder.name
            for folder in self.course_path.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        )

    def first_step(self):
        return 0

    def get_step(self,index):
        if not isinstance(index, int) or index < 0 or index >= len(self.steps):
            return {"type":PageType.END}
        return self.steps[index]

    def next_step(self,index):
        if not isinstance(index, int):
            return len(self.steps)
        return min(index + 1, len(self.steps))

    def check_answer(self,step,selected):
        if not isinstance(step, dict) or step.get("type") != PageType.MCQ:
            return False
        options = step.get("options")
        answer = step.get("answer")
        if not isinstance(options, list) or not isinstance(selected, int):
            return False
        if not 0 <= selected < len(options):
            return False
        return selected == answer

    def on_event(self,event,**kwargs):
        self.events.append({"event":event,**kwargs})
        if event=="answer_submitted":
            sid=kwargs.get("step_id",0)
            step=self.get_step(sid)
            if (
                step.get("type") == PageType.MCQ
                and sid not in self.answered_step_ids
                and self.check_answer(step, kwargs.get("answer"))
                and kwargs.get("correct")
            ):
                self.score+=1
            if step.get("type") == PageType.MCQ:
                self.answered_step_ids.add(sid)
        elif event=="time_expired":
            print(f"Timeout on step {kwargs.get('step_id')}")
        elif event=="chapter_started":
            self.score=0
            self.answered_step_ids.clear()
        elif event=="chapter_closed":
            print("Chapter closed")
        return {"score":self.score,"events":len(self.events)}

    def analytics(self):
        return {"score":self.score,"total_events":len(self.events)}
