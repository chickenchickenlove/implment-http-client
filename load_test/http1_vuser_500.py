import httpx
from locust import HttpUser, task, constant, TaskSet, User
from locust import LoadTestShape


class UserBehavior(TaskSet):

    @task
    def get(self):
        self.client.get('/hello/ballo')


class LoadTestUser(HttpUser):
    host = 'http://localhost:8081'
    wait_time = constant(1)
    tasks = [UserBehavior]


SPAWN_RATE = 100
class StagesShape(LoadTestShape):

    stages = [
        {"duration": 1000, "users": 500, "spawn_rate": SPAWN_RATE},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage['duration']:
                return (stage['users'], stage['spawn_rate'])
        return None
