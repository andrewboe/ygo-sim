"""Minimal PE64 reader for duel.dll: sections, exports, function table (.pdata), RIP-relative references."""
import bisect
import re
import struct


class PE:
    def __init__(self, path):
        self.b = b = open(path, "rb").read()
        pe = struct.unpack_from("<I", b, 0x3C)[0]
        nsec, osz = struct.unpack_from("<H", b, pe + 6)[0], struct.unpack_from("<H", b, pe + 20)[0]
        opt = pe + 24
        self.base = struct.unpack_from("<Q", b, opt + 24)[0]
        self.dirs = opt + 112
        self.sections = {}
        for k in range(nsec):
            name, vsize, va, rsize, raw = struct.unpack_from("<8sIIII", b, opt + osz + k * 40)
            self.sections[name.rstrip(b"\0").decode()] = (va, vsize, raw, rsize)
        va, vsize, raw, _ = self.sections[".pdata"]
        funcs = (struct.unpack_from("<III", b, raw + k * 12) for k in range(vsize // 12))
        self.funcs = sorted((s, e) for s, e, _ in funcs if s)
        self.starts = [s for s, _ in self.funcs]

    def off(self, rva):
        for va, vsize, raw, rsize in self.sections.values():
            if va <= rva < va + max(vsize, rsize):
                return rva - va + raw
        return None

    def rva(self, off):
        for va, vsize, raw, rsize in self.sections.values():
            if raw <= off < raw + rsize:
                return off - raw + va
        return None

    def section(self, name):
        va, vsize, raw, _ = self.sections[name]
        return va, self.b[raw:raw + vsize]

    def function_at(self, rva):
        """Start RVA of the .pdata function range containing rva (None outside any)."""
        k = bisect.bisect_right(self.starts, rva) - 1
        return self.funcs[k][0] if k >= 0 and self.funcs[k][0] <= rva < self.funcs[k][1] else None

    def exports(self) -> dict:
        erva = struct.unpack_from("<I", self.b, self.dirs)[0]
        o = self.off(erva)
        _, n_names, a_funcs, a_names, a_ords = struct.unpack_from("<IIIII", self.b, o + 20)
        out = {}
        for k in range(n_names):
            nrva = struct.unpack_from("<I", self.b, self.off(a_names) + 4 * k)[0]
            no = self.off(nrva)
            name = self.b[no:self.b.index(b"\0", no)].decode()
            ordinal = struct.unpack_from("<H", self.b, self.off(a_ords) + 2 * k)[0]
            out[name] = struct.unpack_from("<I", self.b, self.off(a_funcs) + 4 * ordinal)[0]
        return out

    def rip_refs(self, targets) -> dict:
        """target RVA -> RVAs of .text displacement fields whose rip-relative target it is."""
        targets = set(targets)
        va, text = self.section(".text")
        out = {}
        for k in range(4):
            seg = text[k:len(text) - (len(text) - k) % 4]
            for j, (disp,) in enumerate(struct.iter_unpack("<i", seg)):
                at = va + k + 4 * j
                t = at + 4 + disp
                if t in targets:
                    out.setdefault(t, []).append(at)
        return out

    def calls(self):
        """(caller function, callee function) pairs for direct rel32 calls."""
        va, text = self.section(".text")
        starts = set(self.starts)
        for m in re.finditer(rb"\xe8", text):
            p = m.start()
            if p + 5 > len(text):
                break
            t = va + p + 5 + struct.unpack_from("<i", text, p + 1)[0]
            if t in starts:
                s = self.function_at(va + p)
                if s is not None:
                    yield s, t
