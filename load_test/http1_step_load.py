from locust import HttpUser, task, constant, TaskSet, User
from locust import LoadTestShape


class UserBehavior(TaskSet):

    @task
    def get(self):
        self.client.get('/hello/ballo')


class LoadTestUser(HttpUser):
    host = 'http://localhost:8080'
    wait_time = constant(1)
    tasks = [UserBehavior]


SPAWN_RATE = 100
class StagesShape(LoadTestShape):

    stages = [
        {"duration": 30, "users": 200, "spawn_rate": SPAWN_RATE},
        {"duration": 60, "users": 400, "spawn_rate": SPAWN_RATE},
        {"duration": 90, "users": 600, "spawn_rate": SPAWN_RATE},
        {"duration": 120, "users": 800, "spawn_rate": SPAWN_RATE},
        {"duration": 150, "users": 1000, "spawn_rate": SPAWN_RATE},
        {"duration": 180, "users": 1200, "spawn_rate": SPAWN_RATE},
        {"duration": 210, "users": 1400, "spawn_rate": SPAWN_RATE},
        {"duration": 240, "users": 1600, "spawn_rate": SPAWN_RATE},
        {"duration": 270, "users": 1800, "spawn_rate": SPAWN_RATE},
        {"duration": 300, "users": 2000, "spawn_rate": SPAWN_RATE},
        {"duration": 330, "users": 2200, "spawn_rate": SPAWN_RATE},
        {"duration": 360, "users": 2400, "spawn_rate": SPAWN_RATE},
        {"duration": 390, "users": 2600, "spawn_rate": SPAWN_RATE},
        {"duration": 420, "users": 2800, "spawn_rate": SPAWN_RATE},
        {"duration": 450, "users": 3000, "spawn_rate": SPAWN_RATE},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage['duration']:
                return (stage['users'], stage['spawn_rate'])
        return None
