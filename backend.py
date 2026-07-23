import json
from enum import Enum
from pathlib import Path

from llm import OllamaListener

class PageType(Enum):
    CATEGORY="category"
    THEORY="theory"
    MCQ="mcq"
    SUBJECTIVE="subjective"
    END="end"

class LearningBackend:
    def __init__(self, course_path=None, llm_client=None):
        project_path = Path(__file__).resolve().parent
        self.course_path = project_path / "course" if course_path is None else Path(course_path)
        self.llm = llm_client or OllamaListener()
        self.score=0
        self.events=[]
        self.answered_step_ids=set()
        self.steps=[]

    def get_categories(self):
        """Return visible subject folders from the configured course directory."""
        if not self.course_path.is_dir():
            return []
        return sorted(
            folder.name
            for folder in self.course_path.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        )

    def start_course(self, category):
        """Start a fresh, generated learning session for one subject."""
        self.steps.clear()
        self.on_event("chapter_started", category=category)

    def generate_step(self, category, thought):
        """Create and store one theory explanation or practice question from a learner prompt."""
        if not isinstance(thought, str) or not thought.strip():
            raise ValueError("Enter what you would like to learn or practise.")

        prompt = (
            f"Subject: {category}\n"
            f"Learner request: {thought.strip()}\n\n"
            "Decide whether the request is best answered with theory or a practice question. "
            "Return exactly one JSON object. For theory use: "
            '{"type":"theory","title":"short title","content":"clear concise explanation"}. '
            "For practice use: "
            '{"type":"mcq","question":"question","options":["option 1","option 2","option 3","option 4"],'
            '"answer_index":0,"explanation":"why the answer is correct"}. '
            "Use theory for explanation, definition, or concept requests. Use an MCQ when the learner asks "
            "for a question, quiz, practice, or a similar question. Keep all content accurate, age-appropriate, and relevant."
        )
        system_prompt = "You are a helpful education assistant. Return valid JSON only; do not use Markdown fences."
        response = self.llm.chat(prompt, system_prompt=system_prompt)
        step = self._parse_generated_step(response)
        self.steps.append(step)
        return len(self.steps) - 1

    @staticmethod
    def _parse_generated_step(response):
        try:
            data = json.loads(response)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return a valid lesson. Please try again.") from error
        if not isinstance(data, dict):
            raise ValueError("The model returned an invalid lesson format. Please try again.")

        step_type = data.get("type")
        if step_type == "theory":
            title = data.get("title")
            content = data.get("content")
            if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
                return {"type": PageType.THEORY, "title": title.strip(), "content": content.strip()}

        if step_type == "mcq":
            question = data.get("question")
            options = data.get("options")
            answer_index = data.get("answer_index")
            explanation = data.get("explanation")
            valid_options = (
                isinstance(options, list)
                and len(options) == 4
                and all(isinstance(option, str) and option.strip() for option in options)
                and len({option.strip().casefold() for option in options}) == 4
            )
            if (
                isinstance(question, str) and question.strip()
                and valid_options
                and isinstance(answer_index, int) and not isinstance(answer_index, bool)
                and 0 <= answer_index < len(options)
                and isinstance(explanation, str) and explanation.strip()
            ):
                return {
                    "type": PageType.MCQ,
                    "question": question.strip(),
                    "options": [option.strip() for option in options],
                    "answer": answer_index,
                    "explanation": explanation.strip(),
                }

        raise ValueError("The model returned an incomplete lesson. Please try again.")

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
