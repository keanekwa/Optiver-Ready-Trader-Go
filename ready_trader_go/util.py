# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import ipaddress
import socket
import sys

from typing import Callable, Optional, Tuple


async def create_datagram_endpoint(loop: asyncio.AbstractEventLoop,
                                   protocol_factory: Callable[[], asyncio.DatagramProtocol],
                                   local_addr: Optional[Tuple[str, int]] = None,
                                   remote_addr: Optional[Tuple[str, int]] = None, *, family: int = 0, proto: int = 0,
                                   flags: int = 0, reuse_port: Optional[bool] = None,
                                   allow_broadcast: Optional[bool] = None, sock: Optional[socket.socket] = None,
                                   interface: Optional[str] = None
                                   ) -> Tuple[asyncio.BaseTransport, asyncio.BaseProtocol]:
    """Return a datagram endpoint.

    In the case that a multicast address is supplied, this function creates the
    socket manually.
    """
    if local_addr is not None and ipaddress.ip_address(local_addr[0]).is_multicast:
        sock = socket.socket(family if family else socket.AF_INET, socket.SOCK_DGRAM, proto)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        mreq = socket.inet_aton(local_addr[0]) + socket.inet_aton(interface)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, bytes(mreq))
        sock.bind((interface, local_addr[1]) if sys.platform == "win32" else local_addr)
        return await loop.create_datagram_endpoint(protocol_factory, sock=sock)
    elif remote_addr is not None and ipaddress.ip_address(remote_addr[0]).is_multicast:
        sock = socket.socket(family if family else socket.AF_INET, socket.SOCK_DGRAM, proto)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 0)
        sock.connect(remote_addr)
        return await loop.create_datagram_endpoint(protocol_factory, sock=sock)

    return await loop.create_datagram_endpoint(protocol_factory, local_addr, remote_addr, family=family, proto=proto,
                                               flags=flags, reuse_port=reuse_port, allow_broadcast=allow_broadcast,
                                               sock=sock)
