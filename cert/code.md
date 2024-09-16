openssl req -x509 -newkey rsa:4096 -keyout localhost_key.pem -out localhost_cert.pem -days 365 -nodes -subj "/CN=localhost"


openssl req -x509 -newkey rsa:4096 -keyout example_com_key.pem -out example_com_cert.pem -days 365 -nodes -subj "/CN=example.com"
