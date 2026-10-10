"""Enumerate DirectML's DXGI adapter order without installing a toolchain."""
import ctypes as c
from ctypes import wintypes as w


def dxgi_adapters():
    class GUID(c.Structure):
        _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD),
                    ("Data3", w.WORD), ("Data4", c.c_ubyte * 8)]

    class LUID(c.Structure):
        _fields_ = [("LowPart", w.DWORD), ("HighPart", w.LONG)]

    class DESC(c.Structure):
        _fields_ = [("Description", w.WCHAR * 128), ("VendorId", w.UINT),
                    ("DeviceId", w.UINT), ("SubSysId", w.UINT),
                    ("Revision", w.UINT), ("DedicatedVideoMemory", c.c_size_t),
                    ("DedicatedSystemMemory", c.c_size_t),
                    ("SharedSystemMemory", c.c_size_t), ("AdapterLuid", LUID),
                    ("Flags", w.UINT)]

    def method(ptr, index, result, *args):
        vtable = c.cast(ptr, c.POINTER(c.POINTER(c.c_void_p))).contents
        return c.WINFUNCTYPE(result, c.c_void_p, *args)(vtable[index])

    iid = GUID(0x770aae78, 0xf26f, 0x4dba,
               (c.c_ubyte * 8)(0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87))
    factory = c.c_void_p()
    create = c.WinDLL("dxgi").CreateDXGIFactory1
    create.argtypes = [c.POINTER(GUID), c.POINTER(c.c_void_p)]
    create.restype = w.LONG
    hr = create(c.byref(iid), c.byref(factory))
    if hr < 0:
        raise RuntimeError(f"CreateDXGIFactory1 failed: {hr:#x}")
    adapters = []
    try:
        enum = method(factory, 12, w.LONG, w.UINT, c.POINTER(c.c_void_p))
        for index in range(32):
            adapter = c.c_void_p()
            hr = enum(factory, index, c.byref(adapter))
            if c.c_uint32(hr).value == 0x887a0002:
                break
            if hr < 0:
                raise RuntimeError(f"EnumAdapters1 failed: {hr:#x}")
            try:
                desc = DESC()
                hr = method(adapter, 10, w.LONG, c.POINTER(DESC))(adapter, c.byref(desc))
                if hr < 0:
                    raise RuntimeError(f"GetDesc1 failed: {hr:#x}")
                adapters.append({"index": index, "name": desc.Description,
                                 "vendor_id": desc.VendorId,
                                 "vram_bytes": desc.DedicatedVideoMemory})
            finally:
                method(adapter, 2, w.ULONG)(adapter)
    finally:
        method(factory, 2, w.ULONG)(factory)
    return adapters


if __name__ == "__main__":
    import json
    print(json.dumps(dxgi_adapters(), indent=2))
