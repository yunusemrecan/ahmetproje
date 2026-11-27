"""{{name}}: {{t:api_doc}}"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="{{name}}",
    description="{{t:api_desc}}",
)


class TaskIn(BaseModel):
    title: str


class Task(TaskIn):
    id: int
    done: bool = False


# {{t:api_memory_comment}}
tasks: dict[int, Task] = {}
next_id = 1


@app.get("/")
def home() -> dict[str, str]:
    return {
        "message": "{{t:api_hello}}",
        "docs": "/docs",
    }


@app.get("/tasks")
def list_tasks() -> list[Task]:
    return list(tasks.values())


@app.post("/tasks", status_code=201)
def add_task(task: TaskIn) -> Task:
    global next_id
    created = Task(id=next_id, title=task.title)
    tasks[created.id] = created
    next_id += 1
    return created


@app.post("/tasks/{task_id}/done")
def complete_task(task_id: int) -> Task:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="{{t:api_not_found}}")
    task.done = True
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int) -> None:
    if tasks.pop(task_id, None) is None:
        raise HTTPException(status_code=404, detail="{{t:api_not_found}}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
