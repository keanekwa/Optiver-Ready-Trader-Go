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
import mmap
import os
import struct

from typing import Coroutine, Optional, Tuple, Union

BUFFER_SIZE = 8192
FRAME_HEADER_SIZE = 8
FRAME_SIZE = 128
MAXIMUM_PAYLOAD_LENGTH = FRAME_SIZE - FRAME_HEADER_SIZE


class Publisher(asyncio.WriteTransport):
    """Publisher side of a datagram transport based on shared memory.

    Transport is achieved through the use of memory mapped files or shared
    memory blocks. There must be an interval between writes to permit
    subscribers to read the data before it is overwritten.
    """
    __slots__ = ("__pack_into", "_buffer", "_closed", "_pos")

    def __init__(self, buffer: Union[mmap.mmap, memoryview], protocol: asyncio.BaseProtocol):
        super().__init__()
        self._buffer: Optional[Union[mmap.mmap, memoryview]] = buffer
        self._closed: bool = False
        self._pos: int = 0
        asyncio.get_event_loop().call_soon(protocol.connection_made, self)

        self.__pack_into = struct.Struct("!I").pack_into

    def __del__(self):
        if not self._closed:
            self.close()

    def abort(self) -> None:
        """Close the publisher immediately."""
        self.close()

    def can_write_eof(self) -> bool:
        """Return False. Publisher's don't support writing EOF."""
        return False

    def close(self) -> None:
        """Close the publisher."""
        self._closed = True

    def write(self, data: Union[bytearray, bytes, memoryview]) -> None:
        """Publish the provided data."""
        if len(data) > MAXIMUM_PAYLOAD_LENGTH:
            raise ValueError("payload is longer than maximum payload length")

        if self._closed:
            return

        # Each frame contains a spinlock (4 bytes), payload length (4 bytes)
        # and payload (up to 120 bytes).
        pos = self._pos
        self.__pack_into(self._buffer, pos + 4, len(data))
        start: int = pos + FRAME_HEADER_SIZE
        self._buffer[start:start + len(data)] = bytes(data)
        self._pos = (pos + FRAME_SIZE) & (BUFFER_SIZE - 1)
        self._buffer[self._pos] = 0
        self._buffer[pos] = 1


class MmapPublisher(Publisher):
    """A publisher based on a memory mapped file."""
    __slots__ = ("__fileno",)

    def __init__(self, fileno: int, mm: mmap.mmap, protocol: asyncio.BaseProtocol):
        super().__init__(mm, protocol)
        self.__fileno: Optional[int] = fileno

    def close(self) -> None:
        """Close the publisher."""
        super().close()
        if self._buffer:
            self._buffer.close()
            self._buffer = None
        if self.__fileno:
            os.close(self.__fileno)
            self.__fileno = None


class Subscriber(asyncio.DatagramTransport):
    """Subscriber side of a datagram transport based on shared memory.

    Transport is achieved through the use of memory mapped files or shared
    memory blocks. An interval between writes gives subscribers time to read
    the data before it is overwritten and the subscriber polls the shared
    memory in order to pick up changes as soon as possible.
    """
    __slots__ = ("_task", "_closed", "_protocol")

    def __init__(self, buffer: Union[mmap.mmap, memoryview], from_addr: Tuple[str, int],
                 protocol: asyncio.DatagramProtocol):
        super().__init__()
        self._closed: bool = False
        self._protocol: asyncio.DatagramProtocol = protocol

        coro: Coroutine = self._subscribe_worker(buffer, from_addr, protocol)
        self._task: asyncio.Task = asyncio.ensure_future(coro)

    async def _subscribe_worker(self, buffer: Union[mmap.mmap, memoryview],
                                from_addr: Tuple[str, int],
                                protocol: asyncio.DatagramProtocol) -> None:
        mask: int = BUFFER_SIZE - 1
        unpack_from = struct.Struct("!I").unpack_from
        protocol.connection_made(self)

        try:
            pos: int = 0
            while not self._closed:
                while buffer[pos] == 0:
                    await asyncio.sleep(0.0)
                length, = unpack_from(buffer, pos + 4)
                start: int = pos + FRAME_HEADER_SIZE
                protocol.datagram_received(buffer[start:start + length], from_addr)
                pos = (pos + FRAME_SIZE) & mask
        except asyncio.CancelledError:
            self._protocol.connection_lost(None)
        except Exception as e:
            self._protocol.connection_lost(e)

    def abort(self) -> None:
        """Close the transport immediately."""
        self.close()

    def is_closing(self):
        """Return True if the subscriber is closing or is closed."""
        return self._closed

    def close(self) -> None:
        """Close the subscriber."""
        if not self._closed:
            self._task.cancel()
            self._closed = True

    def get_protocol(self) -> asyncio.DatagramProtocol:
        """Return the current protocol."""
        return self._protocol

    def sendto(self, data: Union[bytearray, bytes, memoryview],
               addr: Optional[Tuple[str, int]] = None) -> None:
        """Send data to the transport."""
        raise RuntimeError("Attempt to write to a Subscriber (a read-only transport)")


class MmapSubscriber(Subscriber):
    """A subscriber based on a memory mapped file."""
    __slots__ = ("__fileno", "__mmap")

    def __init__(self, fileno: int, buffer: mmap.mmap, from_addr: Tuple[str, int],
                 protocol: Optional[asyncio.DatagramProtocol] = None):
        super().__init__(buffer, from_addr, protocol)
        self.__fileno: Optional[int] = fileno
        self.__mmap: Optional[mmap.mmap] = buffer
        self._task.add_done_callback(lambda _: self.__close_mmap())

    def __del__(self):
        self.__close_mmap()

    def __close_mmap(self):
        if self.__mmap:
            self.__mmap.close()
            self.__mmap = None
        if self.__fileno:
            os.close(self.__fileno)
            self.__fileno = None


class PublisherFactory:
    """A factory class for Publisher instances."""
    def __init__(self, typ: str, name: str):
        if typ not in ("mmap", "shm"):
            raise ValueError("type must be either 'mmap' or 'shm'")
        self.__typ: str = typ
        self.__name: str = name

    @property
    def name(self):
        """Return the name for this publisher factory."""
        return self.__name

    @property
    def typ(self):
        """Return the type for this publisher factory."""
        return self.__typ

    def create(self, protocol: asyncio.BaseProtocol) -> Publisher:
        """Create a new Publisher instance."""
        if self.__typ == "mmap":
            fileno = os.open(self.__name, os.O_CREAT | os.O_RDWR)
            os.write(fileno, b"\x00" * BUFFER_SIZE)
            buffer = mmap.mmap(fileno, BUFFER_SIZE, access=mmap.ACCESS_WRITE)
            return MmapPublisher(fileno, buffer, protocol)
        raise RuntimeError("PublisherFactory type was not 'mmap'")


class SubscriberFactory:
    """A factory class for Subscribers."""
    def __init__(self, typ: str, name: str):
        if typ not in ("mmap", "shm"):
            raise ValueError("type must be either 'mmap' or 'shm'")
        self.__typ: str = typ
        self.__name: str = name

    @property
    def name(self):
        """Return the name for this subscriber factory."""
        return self.__name

    @property
    def typ(self):
        """Return the type for this subscriber factory."""
        return self.__typ

    def create(self, protocol: Optional[asyncio.DatagramProtocol] = None) -> Subscriber:
        """Return a new Subscriber instance."""
        if self.__typ == "mmap":
            fileno = os.open(self.__name, os.O_RDONLY)
            mm = mmap.mmap(fileno, BUFFER_SIZE, access=mmap.ACCESS_READ)
            return MmapSubscriber(fileno, mm, (self.__name, fileno), protocol)
        raise RuntimeError("SubscriberFactory type was not 'mmap'")
