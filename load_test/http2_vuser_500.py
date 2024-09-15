import socket
from locust import User, task, constant, LoadTestShape
import time
from h2.connection import H2Connection
from h2.events import ResponseReceived, DataReceived, StreamEnded


HOST = 'localhost'
PORT = 8080

class H2LoadTestUser(User):
    wait_time = constant(1)

    def on_start(self) -> None:
        self.host = HOST
        self.port = PORT
        self.sock = socket.create_connection((self.host, self.port))
        self.should_initiate = True
        self.conn = H2Connection()
        self.conn.initiate_connection()
        self.sock.sendall(self.conn.data_to_send())

    @task
    def get(self):

        start_time = time.time()
        try:

            request_headers = [
                (':method', 'GET'),
                (':path', '/hello/ballo'),
                (':authority', self.host),
                (':scheme', 'http'),
            ]

            stream_id = self.conn.get_next_available_stream_id()
            self.conn.send_headers(stream_id, request_headers, end_stream=True)
            self.sock.sendall(self.conn.data_to_send())

            response_headers = []
            response_data = b""
            stream_ended = False

            while not stream_ended:
                data = self.sock.recv(65535)
                if not data:
                    break

                events = self.conn.receive_data(data)
                for event in events:
                    if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                        response_headers.extend(event.headers)
                    elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                        response_data += event.data

                        self.conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
                    elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                        stream_ended = True
                self.sock.sendall(self.conn.data_to_send())

            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(request_type="GET",
                                                 name="/hello/ballo",
                                                 response_time=total_time,
                                                 response_length=0,
                                                 exception=None,
                                                 )

        except ConnectionResetError as e:
            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(
                request_type="GET",
                name="/hello/ballo",
                response_time=total_time,
                response_length=0,
                exception=e
            )
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(
                request_type="GET",
                name="/hello/ballo",
                response_time=total_time,
                response_length=0,
                exception=e
            )


    def on_stop(self):
        self.conn.close_connection()
        self.sock.sendall(self.conn.data_to_send())

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
