### HTTP/2 SPEC TEST
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
