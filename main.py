from __future__ import annotations

import socket
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_lan_ips() -> list[str]:
    ips: set[str] = set()

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None):
            ip = item[4][0]
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                ips.add(ip)
    except Exception:
        pass

    # 备用方案：通过 UDP socket 获取默认出口 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
            ips.add(ip)
    except Exception:
        pass

    return sorted(ips)


def print_access_urls(port: int) -> None:
    print("")
    print("=" * 60)
    print("纯文本剧本审核分析系统已启动")
    print("")
    print(f"本机访问地址：")
    print(f"  http://127.0.0.1:{port}")
    print("")
    print("局域网访问地址候选：")

    lan_ips = get_lan_ips()
    if lan_ips:
        for ip in lan_ips:
            print(f"  http://{ip}:{port}")
    else:
        print("  未自动识别到局域网 IP，请手动运行 ipconfig 查看 IPv4 地址。")

    print("")
    print("给同事访问时，选择和对方电脑处在同一网段的地址。")
    print("例如对方 IP 是 192.168.2.xxx，就用 192.168.2.xxx 同网段地址。")
    print("=" * 60)
    print("")


def main() -> None:
    port = 8001
    print_access_urls(port)

    uvicorn.run(
        "app.review_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()