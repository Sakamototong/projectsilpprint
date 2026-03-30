import socket

HOST = '0.0.0.0'
PORT = 9100

def run():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(1)
        print(f"Printer simulator listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                print('Connected by', addr)
                data = conn.recv(4096)
                while data:
                    print(data.decode(errors='ignore'))
                    data = conn.recv(4096)


if __name__ == '__main__':
    run()
