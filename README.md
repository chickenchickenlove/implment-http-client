# The server implementation which supports both HTTP/1 and HTTP/2
This server is not intended for production use.
I implement this server to understand how low-level web works, low-level HTTP protocol works and Etc.   


### VERSION
- 0.0.0 : skeleton. (HTTP/1, HTTP/2 with h2c protocol)
- 0.0.1
  - Support TLS.
  - Support HTTP/2 with h2 protocol
  - Support Virtual server by port and domain by. 
  - Change interface of using route rule.
  - Fixes bug that can't response completely when there is no route rule at all.
- 0.0.2
  - Support Server Sent Event Feature with HTTP/1.1. 
- 0.0.3
  - Support Connection Context and Request Context to inject parameters to endpoint methods.
  - Internal Refactoring.

### How to use
```python
import asyncio
import time

from http_2.server import Server, AsyncServerExecutor
from http_2.ssl_object import SSLConfig
from http_2.common_http_object import GenericHttpRequest, GenericHttpResponse
from http_2.http1_response import StreamingResponse, GeneralHttp1Response

async def main():

    localhost_ssl_config = SSLConfig()
    localhost_ssl_config.add_tls_with_hostname(
        hostname='localhost',
        certfile_path='...',
        keyfile_path='...')

    example_com_ssl_config = SSLConfig()
    example_com_ssl_config.add_tls_with_hostname(
        hostname='example.com',
        certfile_path='...',
        keyfile_path='...')

    http_localhost_server = Server(8080)
    localhost_server = Server(443, hostname='localhost', ssl_config=localhost_ssl_config)
    example_com_server = Server(443, hostname='example.com', ssl_config=example_com_ssl_config)

    @http_localhost_server.get_mapping(path='/sse')
    async def server_sent_event(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        async def gen_events():
            for _ in range(5):
                await asyncio.sleep(1)
                yield f"data: 현재 시간은 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        return StreamingResponse(gen_events())

    @http_localhost_server.route(path='/', methods=['POST', 'GET'])
    @example_com_server.route(path='/', methods=['POST', 'GET'])
    @localhost_server.route(path='/', methods=['POST', 'GET'])
    async def common(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        return GeneralHttp1Response(body='hello')

    executor = AsyncServerExecutor()
    executor.add_server(http_localhost_server)
    executor.add_server(localhost_server)
    executor.add_server(example_com_server)

    async with executor:
        await executor.execute_forever()

if __name__ == '__main__':
    asyncio.run(main())
```

### How to test

#### For Unit and Integration Test
```shell
$ py.test ./tests/
```

#### For HTTP/2 Spec test

```shell
$ brew install h2spec
$ cd http_h2
$ python main.py
...

$ h2spec -p 8080 -h localhost 
>>
Generic tests for HTTP/2 server
  1. Starting HTTP/2
    ✔ 1: Sends a client connection preface
    ...

Hypertext Transfer Protocol Version 2 (HTTP/2)
  3. Starting HTTP/2
    3.5. HTTP/2 Connection Preface
      ✔ 1: Sends client connection preface
      ✔ 2: Sends invalid connection preface
    ...

HPACK: Header Compression for HTTP/2
  2. Compression Process Overview
    ...

Finished in 0.2501 seconds
146 tests, 145 passed, 1 skipped, 0 failed
```


## Performance `HTTP/1`
- HTTP/1 Condition
  - Local M1 Mac.
  - `Locust` load test. 
  - `FastAPI` with `uvicorn`. 
  - Custom Server.
  - Using `keep-alive`.

RPS

| Server Type   | Type | Name          | # Requests | # Fails | Average (ms) | Min (ms) | Max (ms) | Average size (bytes) | RPS    | Failures/s |
|---------------|------|---------------|------------|---------|--------------|----------|----------|----------------------|--------|------------|
| CUSTOM SERVER | GET  | /hello/ballo  | 659853     | 0       | 69.16        | 0        | 1189     | 1                    | 1461.36| 0          |
| FAST API      | GET  | /hello/ballo  | 552122     | 0       | 244.37       | 0        | 6732     | 1                    | 1220.07|            |


Response Time

| Server Type   | Method | Name          | 50%ile (ms) | 60%ile (ms) | 70%ile (ms) | 80%ile (ms) | 90%ile (ms) | 95%ile (ms) | 99%ile (ms) | 100%ile (ms) |
|---------------|--------|---------------|-------------|-------------|-------------|-------------|-------------|-------------|-------------|--------------|
| CUSTOM SERVER | GET    | /hello/ballo  | 35          | 49          | 69          | 100         | 160         | 230         | 640         | 1200         |
| FAST API      | GET    | /hello/ballo  | 93          | 190         | 310         | 440         | 650         | 820         | 1300        | 6700         |


## Performance `HTTP/2`
- HTTP/2 Condition
  - Local M1 Mac.
  - `Locust` load test. (h2 client was integrated to `locust`).
  - `FastAPI` with `hypercorn` (Note that `uvicorn` seems to have not HTTP/2 compatibility.
  - Custom Server

RPS

| Server Type   | Type | Name          | # Requests | # Fails | Average (ms) | Min (ms) | Max (ms) | Average size (bytes) | RPS    | Failures/s |
|---------------|------|---------------|------------|---------|--------------|----------|----------|----------------------|--------|------------|
| Custom Server | GET  | /hello/ballo  | 705092     | 0       | 15.71        | 0        | 290      | 0                    | 1564.11| 0          |
| FAST API      | GET  | /hello/ballo  | 500745     | 0       | 429.87       | 0        | 3893     | 0                    | 1111.84| 0          |

Response Time

| Server Type   | Method | Name          | 50%ile (ms) | 60%ile (ms) | 70%ile (ms) | 80%ile (ms) | 90%ile (ms) | 95%ile (ms) | 99%ile (ms) | 100%ile (ms) |
|---------------|--------|---------------|-------------|-------------|-------------|-------------|-------------|-------------|-------------|--------------|
| Custom Server | GET    | /hello/ballo  | 9           | 12          | 16          | 21          | 33          | 56          | 120         | 290          |
| FAST API      | GET    | /hello/ballo  | 200         | 360         | 730         | 960         | 1200        | 1300        | 1400        | 3900         |
