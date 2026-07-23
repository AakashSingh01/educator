from enum import Enum

class PageType(Enum):
    CATEGORY="category"
    THEORY="theory"
    MCQ="mcq"
    SUBJECTIVE="subjective"
    END="end"

class LearningBackend:
    def __init__(self):
        self.score=0
        self.events=[]
        self.steps=[
            {"type":PageType.THEORY,"title":"Introduction","content":"Welcome to the chapter. Read before continuing.","time_limit":200},
            {"type":PageType.MCQ,"question":"2 + 5 = ?","options":["5","6","7","8"],"answer":2,"explanation":"2+5=7","time_limit":30},
            {"type":PageType.SUBJECTIVE,"question":"Explain why prime numbers are useful.","time_limit":60},
            {"type":PageType.MCQ,"question":"Square root of 81?","options":["7","8","9","10"],"answer":2,"explanation":"9×9=81","time_limit":30},
        ]

    def first_step(self):
        return 0

    def get_step(self,index):
        if index>=len(self.steps):
            return {"type":PageType.END}
        return self.steps[index]

    def next_step(self,index):
        return index+1

    def check_answer(self,step,selected):
        return selected==step["answer"]

    def on_event(self,event,**kwargs):
        self.events.append({"event":event,**kwargs})
        if event=="answer_submitted":
            sid=kwargs.get("step_id",0)
            step=self.get_step(sid)
            if step.get("type")==PageType.MCQ and kwargs.get("correct"):
                self.score+=1
        elif event=="time_expired":
            print(f"Timeout on step {kwargs.get('step_id')}")
        elif event=="chapter_started":
            self.score=0
        elif event=="chapter_closed":
            print("Chapter closed")
        return {"score":self.score,"events":len(self.events)}

    def analytics(self):
        return {"score":self.score,"total_events":len(self.events)}
