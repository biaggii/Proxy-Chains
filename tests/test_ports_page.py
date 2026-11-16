from models.port_mapping import PortMapping, format_proxy_endpoints


def test_http_and_socks_proxy_endpoint_formats() -> None:
    mappings = [
        PortMapping(listen_port=20002, chain_id="chain-a"),
        PortMapping(listen_port=20003, chain_id="chain-b", listen_host="::1"),
    ]

    assert format_proxy_endpoints(mappings, "http") == (
        "http://127.0.0.1:20002\nhttp://[::1]:20003"
    )
    assert format_proxy_endpoints(mappings, "socks5") == (
        "socks5://127.0.0.1:20002\nsocks5://[::1]:20003"
    )
