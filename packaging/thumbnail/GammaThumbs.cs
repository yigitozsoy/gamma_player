// gamma — Windows Gezgini için 3D model küçük resim sağlayıcısı (IThumbnailProvider).
// STL (ikili / ASCII), OBJ, PLY, OFF, GLB ve glTF dosyalarını yazılımla çizip saydam arka planlı
// bir küçük resim döndürür. GLB/glTF'de malzeme rengi ve doku (PNG/JPEG), PLY/OFF'ta köşe/yüz renkleri kullanılır.
// Gezgin, küçük resmin köşesine varsayılan uygulamanın (gamma) simgesini kendisi ekler.
//
// Derleme (build.ps1 yapar; .NET Framework 4 her Windows 10/11'de var, C# 5):
//   csc /target:library /optimize+ /r:System.Drawing.dll /out:GammaThumbs.dll GammaThumbs.cs
// Kayıt: regasm gerekmez; kurulum HKCU\Software\Classes\CLSID altına mscoree.dll + CodeBase yazar.
//   Provider      (akıştan okur)  : .stl .obj .ply .off .glb
//   FileProvider  (yoldan okur)   : .gltf — harici .bin ve doku dosyaları yanındaki klasörden okunur
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]

namespace GammaThumbs
{
    [ComImport, Guid("b824b49d-22ac-4161-ac8a-9916e8fa3f7f"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IInitializeWithStream
    {
        void Initialize(IStream pstream, uint grfMode);
    }

    [ComImport, Guid("b7d14566-0509-4cce-a71f-0a554233bd9b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IInitializeWithFile
    {
        void Initialize([MarshalAs(UnmanagedType.LPWStr)] string pszFilePath, uint grfMode);
    }

    [ComImport, Guid("e357fccd-a995-4576-b01f-234630154e96"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IThumbnailProvider
    {
        void GetThumbnail(uint cx, out IntPtr phbmp, out uint pdwAlpha);
    }

    static class Thumb
    {
        // Gezgin'in içinde çalıştığı için (DisableProcessIsolation) çok büyük dosyalar atlanır
        public const long MaxBytes = 200L * 1024 * 1024;

        public static IntPtr Make(Mesh m, uint cx)
        {
            if (m == null || m.P == null || m.P.Length < 9)
                throw new COMException("empty", unchecked((int)0x80004005));
            int size = (int)Math.Max(16, Math.Min(cx, 1024));
            int[] px = Renderer.Render(m, size);
            IntPtr h = Dib.Create(px, size, size);
            if (h == IntPtr.Zero)
                throw new COMException("dib", unchecked((int)0x80004005));
            return h;
        }
    }

    [ComVisible(true), Guid("7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31"), ClassInterface(ClassInterfaceType.None)]
    public class Provider : IInitializeWithStream, IThumbnailProvider
    {
        byte[] data;

        public void Initialize(IStream pstream, uint grfMode)
        {
            System.Runtime.InteropServices.ComTypes.STATSTG st;
            pstream.Stat(out st, 1);   // STATFLAG_NONAME
            if (st.cbSize <= 0 || st.cbSize > Thumb.MaxBytes)
                throw new COMException("size", unchecked((int)0x80004005));
            data = new byte[st.cbSize];
            int off = 0;
            IntPtr pRead = Marshal.AllocCoTaskMem(4);
            try
            {
                while (off < data.Length)
                {
                    int want = Math.Min(1 << 20, data.Length - off);
                    byte[] buf = new byte[want];
                    pstream.Read(buf, want, pRead);
                    int got = Marshal.ReadInt32(pRead);
                    if (got <= 0) break;
                    Buffer.BlockCopy(buf, 0, data, off, got);
                    off += got;
                }
            }
            finally { Marshal.FreeCoTaskMem(pRead); }
            Marshal.ReleaseComObject(pstream);
            if (off < data.Length) Array.Resize(ref data, off);
        }

        public void GetThumbnail(uint cx, out IntPtr phbmp, out uint pdwAlpha)
        {
            pdwAlpha = 2;   // WTSAT_ARGB
            Mesh m = Loader.Load(data, null);
            data = null;
            phbmp = Thumb.Make(m, cx);
        }
    }

    [ComVisible(true), Guid("437a1563-8258-4e3c-80de-511965bd614c"), ClassInterface(ClassInterfaceType.None)]
    public class FileProvider : IInitializeWithFile, IThumbnailProvider
    {
        string path;

        public void Initialize(string pszFilePath, uint grfMode) { path = pszFilePath; }

        public void GetThumbnail(uint cx, out IntPtr phbmp, out uint pdwAlpha)
        {
            pdwAlpha = 2;
            FileInfo fi = new FileInfo(path);
            if (!fi.Exists || fi.Length <= 0 || fi.Length > Thumb.MaxBytes)
                throw new COMException("size", unchecked((int)0x80004005));
            Mesh m = Loader.Load(File.ReadAllBytes(path), Path.GetDirectoryName(path));
            phbmp = Thumb.Make(m, cx);
        }
    }

    // ------------------------------------------------------------------ model verisi
    class Mat
    {
        public float R = 0.78f, G = 0.78f, B = 0.80f;
        public int[] Tex;   // ARGB, satır satır (üstten)
        public int TW, TH;
    }

    class Mesh
    {
        public float[] P;    // üçgen başına 9 (x y z ×3)
        public float[] C;    // üçgen başına 9 (r g b ×3, 0..1) ya da null
        public float[] UV;   // üçgen başına 6 ya da null
        public int[] M;      // üçgen başına malzeme ya da null (hepsi 0)
        public List<Mat> Mats = new List<Mat>();
        public bool ZUp;

        public static Mesh Plain(float[] p, bool zUp)
        {
            Mesh m = new Mesh();
            m.P = p; m.ZUp = zUp;
            m.Mats.Add(new Mat());
            return m;
        }
    }

    // ------------------------------------------------------------------ okuma
    static class Loader
    {
        public static Mesh Load(byte[] d, string dir)
        {
            if (d == null || d.Length < 15) return null;
            if (d[0] == 'g' && d[1] == 'l' && d[2] == 'T' && d[3] == 'F') return Gltf.Load(d, dir);
            if (d.Length >= 84)
            {
                uint n = BitConverter.ToUInt32(d, 80);
                if (n > 0 && 84L + 50L * n == d.Length) return Mesh.Plain(BinaryStl(d, n), true);
            }
            string head = Encoding.ASCII.GetString(d, 0, Math.Min(d.Length, 4096));
            string trimmed = head.TrimStart();
            if (trimmed.StartsWith("ply")) return Ply.Load(d);
            if (trimmed.StartsWith("{")) return Gltf.Load(d, dir);
            if (trimmed.StartsWith("solid", StringComparison.OrdinalIgnoreCase) && head.Contains("facet"))
                return Mesh.Plain(AsciiStl(d), true);
            if (IsOff(trimmed)) return Off(d);
            if (d.Length >= 84)
            {
                uint n = BitConverter.ToUInt32(d, 80);
                if (n > 0 && 84L + 50L * n <= d.Length) return Mesh.Plain(BinaryStl(d, n), true);
            }
            return Mesh.Plain(Obj(d), false);
        }

        static bool IsOff(string head)
        {
            int i = 0;
            while (i < head.Length && !char.IsWhiteSpace(head[i])) i++;
            string tok = head.Substring(0, i);
            return tok.EndsWith("OFF", StringComparison.Ordinal) && tok.Length <= 6;
        }

        static float[] BinaryStl(byte[] d, uint n)
        {
            float[] t = new float[n * 9];
            int o = 84;
            for (int i = 0; i < n; i++)
            {
                for (int k = 0; k < 9; k++) t[i * 9 + k] = BitConverter.ToSingle(d, o + 12 + k * 4);
                o += 50;
            }
            return t;
        }

        static float[] AsciiStl(byte[] d)
        {
            List<float> t = new List<float>();
            using (StreamReader r = new StreamReader(new MemoryStream(d), Encoding.ASCII))
            {
                string line;
                char[] sep = new char[] { ' ', '\t' };
                while ((line = r.ReadLine()) != null)
                {
                    line = line.Trim();
                    if (!line.StartsWith("vertex", StringComparison.OrdinalIgnoreCase)) continue;
                    string[] s = line.Split(sep, StringSplitOptions.RemoveEmptyEntries);
                    if (s.Length < 4) continue;
                    t.Add(F(s[1])); t.Add(F(s[2])); t.Add(F(s[3]));
                }
            }
            int m = t.Count / 9 * 9;
            if (m < t.Count) t.RemoveRange(m, t.Count - m);
            return t.ToArray();
        }

        static float[] Obj(byte[] d)
        {
            List<float> v = new List<float>();
            List<float> t = new List<float>();
            char[] sep = new char[] { ' ', '\t' };
            using (StreamReader r = new StreamReader(new MemoryStream(d), Encoding.UTF8))
            {
                string line;
                while ((line = r.ReadLine()) != null)
                {
                    if (line.Length < 2) continue;
                    if (line[0] == 'v' && (line[1] == ' ' || line[1] == '\t'))
                    {
                        string[] s = line.Split(sep, StringSplitOptions.RemoveEmptyEntries);
                        if (s.Length >= 4) { v.Add(F(s[1])); v.Add(F(s[2])); v.Add(F(s[3])); }
                    }
                    else if (line[0] == 'f' && (line[1] == ' ' || line[1] == '\t'))
                    {
                        string[] s = line.Split(sep, StringSplitOptions.RemoveEmptyEntries);
                        int nv = v.Count / 3;
                        int[] poly = new int[s.Length - 1];
                        bool ok = true;
                        for (int i = 1; i < s.Length; i++)
                        {
                            string a = s[i];
                            int slash = a.IndexOf('/');
                            if (slash >= 0) a = a.Substring(0, slash);
                            int idx;
                            if (!int.TryParse(a, NumberStyles.Integer, CultureInfo.InvariantCulture, out idx)) { ok = false; break; }
                            idx = idx > 0 ? idx - 1 : nv + idx;
                            if (idx < 0 || idx >= nv) { ok = false; break; }
                            poly[i - 1] = idx;
                        }
                        if (!ok) continue;
                        for (int i = 1; i + 1 < poly.Length; i++)
                        {
                            int[] tri = new int[] { poly[0], poly[i], poly[i + 1] };
                            foreach (int q in tri) { t.Add(v[q * 3]); t.Add(v[q * 3 + 1]); t.Add(v[q * 3 + 2]); }
                        }
                    }
                }
            }
            return t.ToArray();
        }

        // OFF / COFF: ASCII, Z-yukarı; yüz satırında isteğe bağlı RGB
        static Mesh Off(byte[] d)
        {
            List<string> tok = new List<string>();
            using (StreamReader r = new StreamReader(new MemoryStream(d), Encoding.ASCII))
            {
                string line;
                char[] sep = new char[] { ' ', '\t' };
                List<string[]> lines = new List<string[]>();
                while ((line = r.ReadLine()) != null)
                {
                    int h = line.IndexOf('#');
                    if (h >= 0) line = line.Substring(0, h);
                    string[] s = line.Split(sep, StringSplitOptions.RemoveEmptyEntries);
                    if (s.Length > 0) lines.Add(s);
                }
                if (lines.Count < 2) return null;
                int li = 0;
                string[] first = lines[0];
                int nv, nf;
                if (first.Length == 1) { li = 1; nv = int.Parse(lines[1][0]); nf = int.Parse(lines[1][1]); li = 2; }
                else { nv = int.Parse(first[1]); nf = int.Parse(first[2]); li = 1; }
                if (li + nv > lines.Count) return null;
                float[] V = new float[nv * 3];
                for (int k = 0; k < nv; k++)
                {
                    string[] s = lines[li + k];
                    for (int c = 0; c < 3 && c < s.Length; c++) V[k * 3 + c] = F(s[c]);
                }
                List<float> P = new List<float>(), C = new List<float>();
                bool colored = false;
                for (int k = 0; k < nf && li + nv + k < lines.Count; k++)
                {
                    string[] s = lines[li + nv + k];
                    int n = int.Parse(s[0]);
                    if (s.Length < 1 + n || n < 3) continue;
                    float cr = 1, cg = 1, cb = 1;
                    if (s.Length >= 1 + n + 3)
                    {
                        colored = true;
                        cr = F(s[1 + n]); cg = F(s[2 + n]); cb = F(s[3 + n]);
                        if (cr > 1 || cg > 1 || cb > 1) { cr /= 255f; cg /= 255f; cb /= 255f; }
                    }
                    int i0 = Clamp(int.Parse(s[1]), nv);
                    for (int i = 2; i < n; i++)
                    {
                        int i1 = Clamp(int.Parse(s[i]), nv), i2 = Clamp(int.Parse(s[i + 1]), nv);
                        foreach (int q in new int[] { i0, i1, i2 })
                        {
                            P.Add(V[q * 3]); P.Add(V[q * 3 + 1]); P.Add(V[q * 3 + 2]);
                            C.Add(cr); C.Add(cg); C.Add(cb);
                        }
                    }
                }
                Mesh m = Mesh.Plain(P.ToArray(), true);
                if (colored) { m.C = C.ToArray(); m.Mats[0] = WhiteMat(); }
                return m;
            }
        }

        public static Mat WhiteMat()
        {
            Mat w = new Mat();
            w.R = w.G = w.B = 1f;
            return w;
        }

        public static int Clamp(int i, int n) { return i < 0 ? 0 : (i >= n ? n - 1 : i); }

        public static float F(string s)
        {
            float f;
            float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out f);
            return f;
        }
    }

    // ------------------------------------------------------------------ PLY (ASCII / ikili), Z-yukarı
    static class Ply
    {
        class Prop { public string Name; public string Type; public string ListType; }
        class Elem { public string Name; public int Count; public List<Prop> Props = new List<Prop>(); }

        static int Size(string t)
        {
            switch (t)
            {
                case "char": case "int8": case "uchar": case "uint8": return 1;
                case "short": case "int16": case "ushort": case "uint16": return 2;
                case "double": case "float64": return 8;
                default: return 4;
            }
        }

        static double ReadBin(byte[] d, ref int o, string t, bool big)
        {
            int sz = Size(t);
            if (o + sz > d.Length) throw new EndOfStreamException();
            byte[] b = d;
            int p = o;
            if (big != !BitConverter.IsLittleEndian && sz > 1)
            {
                b = new byte[sz];
                for (int i = 0; i < sz; i++) b[i] = d[o + sz - 1 - i];
                p = 0;
            }
            o += sz;
            switch (t)
            {
                case "char": case "int8": return (sbyte)b[p];
                case "uchar": case "uint8": return b[p];
                case "short": case "int16": return BitConverter.ToInt16(b, p);
                case "ushort": case "uint16": return BitConverter.ToUInt16(b, p);
                case "int": case "int32": return BitConverter.ToInt32(b, p);
                case "uint": case "uint32": return BitConverter.ToUInt32(b, p);
                case "double": case "float64": return BitConverter.ToDouble(b, p);
                default: return BitConverter.ToSingle(b, p);
            }
        }

        public static Mesh Load(byte[] d)
        {
            int end = IndexOf(d, Encoding.ASCII.GetBytes("end_header"));
            if (end < 0) return null;
            int body = end;
            while (body < d.Length && d[body] != '\n') body++;
            body++;
            string[] header = Encoding.ASCII.GetString(d, 0, end).Split('\n');
            string fmt = "ascii";
            List<Elem> elems = new List<Elem>();
            char[] sep = new char[] { ' ', '\t', '\r' };
            foreach (string ln in header)
            {
                string[] s = ln.Split(sep, StringSplitOptions.RemoveEmptyEntries);
                if (s.Length == 0) continue;
                if (s[0] == "format" && s.Length > 1) fmt = s[1];
                else if (s[0] == "element" && s.Length > 2) { Elem e = new Elem(); e.Name = s[1]; e.Count = int.Parse(s[2]); elems.Add(e); }
                else if (s[0] == "property" && elems.Count > 0)
                {
                    Prop p = new Prop();
                    if (s[1] == "list" && s.Length > 4) { p.ListType = s[2]; p.Type = s[3]; p.Name = s[4]; }
                    else if (s.Length > 2) { p.Type = s[1]; p.Name = s[2]; }
                    else continue;
                    elems[elems.Count - 1].Props.Add(p);
                }
            }
            bool ascii = fmt == "ascii", big = fmt.Contains("big");
            float[] V = null, VC = null;
            int nv = 0;
            List<int> tris = new List<int>();
            int o = body;
            string[] toks = null;
            int ti = 0;
            if (ascii) toks = Encoding.ASCII.GetString(d, body, d.Length - body).Split(new char[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            try
            {
                foreach (Elem e in elems)
                {
                    bool isV = e.Name == "vertex", isF = e.Name == "face";
                    int ix = -1, iy = -1, iz = -1, ir = -1, ig = -1, ib = -1;
                    bool colScale = false;
                    for (int k = 0; k < e.Props.Count; k++)
                    {
                        string n = e.Props[k].Name;
                        if (n == "x") ix = k; else if (n == "y") iy = k; else if (n == "z") iz = k;
                        else if (n == "red" || n == "r" || n == "diffuse_red") { ir = k; colScale = Size(e.Props[k].Type) == 1; }
                        else if (n == "green" || n == "g" || n == "diffuse_green") ig = k;
                        else if (n == "blue" || n == "b" || n == "diffuse_blue") ib = k;
                    }
                    if (isV)
                    {
                        nv = e.Count;
                        V = new float[nv * 3];
                        if (ir >= 0 && ig >= 0 && ib >= 0) VC = new float[nv * 3];
                    }
                    double[] row = new double[e.Props.Count];
                    for (int i = 0; i < e.Count; i++)
                    {
                        for (int k = 0; k < e.Props.Count; k++)
                        {
                            Prop p = e.Props[k];
                            if (p.ListType == null)
                            {
                                row[k] = ascii ? double.Parse(toks[ti++], NumberStyles.Float, CultureInfo.InvariantCulture) : ReadBin(d, ref o, p.Type, big);
                            }
                            else
                            {
                                int cnt = (int)(ascii ? double.Parse(toks[ti++], CultureInfo.InvariantCulture) : ReadBin(d, ref o, p.ListType, big));
                                int[] poly = isF && (p.Name == "vertex_indices" || p.Name == "vertex_index") ? new int[cnt] : null;
                                for (int c = 0; c < cnt; c++)
                                {
                                    double val = ascii ? double.Parse(toks[ti++], CultureInfo.InvariantCulture) : ReadBin(d, ref o, p.Type, big);
                                    if (poly != null) poly[c] = (int)val;
                                }
                                if (poly != null)
                                    for (int c = 1; c + 1 < cnt; c++) { tris.Add(poly[0]); tris.Add(poly[c]); tris.Add(poly[c + 1]); }
                            }
                        }
                        if (isV)
                        {
                            if (ix >= 0) V[i * 3] = (float)row[ix];
                            if (iy >= 0) V[i * 3 + 1] = (float)row[iy];
                            if (iz >= 0) V[i * 3 + 2] = (float)row[iz];
                            if (VC != null)
                            {
                                float s = colScale ? 1f / 255f : 1f;
                                VC[i * 3] = (float)row[ir] * s; VC[i * 3 + 1] = (float)row[ig] * s; VC[i * 3 + 2] = (float)row[ib] * s;
                            }
                        }
                    }
                }
            }
            catch (Exception) { /* kesik dosya: okunabilen kadarı */ }
            if (V == null || nv == 0 || tris.Count < 3) return null;
            int nt = tris.Count / 3;
            float[] P = new float[nt * 9];
            float[] C = VC != null ? new float[nt * 9] : null;
            for (int i = 0; i < nt * 3; i++)
            {
                int q = Loader.Clamp(tris[i], nv);
                P[i * 3] = V[q * 3]; P[i * 3 + 1] = V[q * 3 + 1]; P[i * 3 + 2] = V[q * 3 + 2];
                if (C != null) { C[i * 3] = VC[q * 3]; C[i * 3 + 1] = VC[q * 3 + 1]; C[i * 3 + 2] = VC[q * 3 + 2]; }
            }
            Mesh m = Mesh.Plain(P, true);
            if (C != null) { m.C = C; m.Mats[0] = Loader.WhiteMat(); }
            return m;
        }

        static int IndexOf(byte[] d, byte[] pat)
        {
            int lim = Math.Min(d.Length - pat.Length, 65536);
            for (int i = 0; i <= lim; i++)
            {
                int k = 0;
                while (k < pat.Length && d[i + k] == pat[k]) k++;
                if (k == pat.Length) return i;
            }
            return -1;
        }
    }

    // ------------------------------------------------------------------ küçük JSON okuyucu (glTF için)
    static class Json
    {
        public static object Parse(string s) { int i = 0; return Val(s, ref i); }

        static void Ws(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }

        static object Val(string s, ref int i)
        {
            Ws(s, ref i);
            if (i >= s.Length) throw new FormatException();
            char c = s[i];
            if (c == '{')
            {
                Dictionary<string, object> o = new Dictionary<string, object>();
                i++; Ws(s, ref i);
                if (s[i] == '}') { i++; return o; }
                while (true)
                {
                    Ws(s, ref i);
                    string k = Str(s, ref i);
                    Ws(s, ref i);
                    i++;   // :
                    o[k] = Val(s, ref i);
                    Ws(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    i++; return o;
                }
            }
            if (c == '[')
            {
                List<object> a = new List<object>();
                i++; Ws(s, ref i);
                if (s[i] == ']') { i++; return a; }
                while (true)
                {
                    a.Add(Val(s, ref i));
                    Ws(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    i++; return a;
                }
            }
            if (c == '"') return Str(s, ref i);
            if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "true", 0, 4) == 0) { i += 4; return true; }
            if (s.Length - i >= 5 && string.CompareOrdinal(s, i, "false", 0, 5) == 0) { i += 5; return false; }
            if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "null", 0, 4) == 0) { i += 4; return null; }
            int st = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            return double.Parse(s.Substring(st, i - st), NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        static string Str(string s, ref int i)
        {
            i++;   // "
            StringBuilder b = new StringBuilder();
            while (s[i] != '"')
            {
                char c = s[i++];
                if (c != '\\') { b.Append(c); continue; }
                char e = s[i++];
                switch (e)
                {
                    case 'n': b.Append('\n'); break;
                    case 't': b.Append('\t'); break;
                    case 'r': b.Append('\r'); break;
                    case 'b': b.Append('\b'); break;
                    case 'f': b.Append('\f'); break;
                    case 'u': b.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                    default: b.Append(e); break;
                }
            }
            i++;
            return b.ToString();
        }
    }

    // ------------------------------------------------------------------ glTF 2.0 / GLB (Y-yukarı)
    class Gltf
    {
        Dictionary<string, object> js;
        List<byte[]> buffers = new List<byte[]>();
        string dir;
        List<float> P = new List<float>(), C = new List<float>(), UV = new List<float>();
        List<int> M = new List<int>();
        bool anyColor, anyUv;
        Mesh mesh = new Mesh();
        Dictionary<int, int> matIndex = new Dictionary<int, int>();
        Dictionary<int, Mat> texCache = new Dictionary<int, Mat>();

        public static Mesh Load(byte[] d, string dir)
        {
            Gltf g = new Gltf();
            g.dir = dir;
            return g.Run(d);
        }

        static object Get(object o, string k)
        {
            Dictionary<string, object> m = o as Dictionary<string, object>;
            object v;
            return m != null && m.TryGetValue(k, out v) ? v : null;
        }

        static List<object> Arr(object o, string k) { return Get(o, k) as List<object>; }

        static int Int(object o, string k, int def)
        {
            object v = Get(o, k);
            return v is double ? (int)(double)v : def;
        }

        static double[] Nums(object o, string k)
        {
            List<object> a = Arr(o, k);
            if (a == null) return null;
            double[] r = new double[a.Count];
            for (int i = 0; i < a.Count; i++) r[i] = a[i] is double ? (double)a[i] : 0;
            return r;
        }

        Mesh Run(byte[] d)
        {
            byte[] bin = null;
            string text;
            if (d[0] == 'g' && d[1] == 'l' && d[2] == 'T' && d[3] == 'F')
            {
                text = null;
                int off = 12;
                while (off + 8 <= d.Length)
                {
                    int ln = BitConverter.ToInt32(d, off);
                    uint typ = BitConverter.ToUInt32(d, off + 4);
                    if (ln < 0 || off + 8 + ln > d.Length) break;
                    if (typ == 0x4E4F534A) text = Encoding.UTF8.GetString(d, off + 8, ln);
                    else if (typ == 0x004E4942) { bin = new byte[ln]; Buffer.BlockCopy(d, off + 8, bin, 0, ln); }
                    off += 8 + ln;
                }
                if (text == null) return null;
            }
            else text = Encoding.UTF8.GetString(d);
            js = Json.Parse(text) as Dictionary<string, object>;
            if (js == null) return null;
            List<object> req = Arr(js, "extensionsRequired");
            if (req != null)
                foreach (object e in req)
                {
                    string s = e as string;
                    if (s == "KHR_draco_mesh_compression" || s == "EXT_meshopt_compression" || s == "KHR_mesh_quantization") return null;
                }
            List<object> bufs = Arr(js, "buffers");
            if (bufs != null)
                foreach (object b in bufs)
                {
                    string uri = Get(b, "uri") as string;
                    if (uri == null) buffers.Add(bin ?? new byte[0]);
                    else buffers.Add(ReadUri(uri) ?? new byte[0]);
                }

            List<object> nodes = Arr(js, "nodes");
            List<object> scenes = Arr(js, "scenes");
            if (scenes != null && scenes.Count > 0 && nodes != null)
            {
                int si = Int(js, "scene", 0);
                if (si >= scenes.Count) si = 0;
                List<object> roots = Arr(scenes[si], "nodes");
                if (roots != null)
                    foreach (object r in roots) Walk(nodes, (int)(double)r, Identity(), 0);
            }
            if (P.Count == 0)
            {
                List<object> meshes = Arr(js, "meshes");
                if (meshes != null)
                    for (int i = 0; i < meshes.Count; i++) AddMesh(i, Identity());
            }
            if (P.Count == 0) return null;
            mesh.P = P.ToArray();
            mesh.C = anyColor ? C.ToArray() : null;
            mesh.UV = anyUv ? UV.ToArray() : null;
            mesh.M = M.ToArray();
            if (mesh.Mats.Count == 0) mesh.Mats.Add(new Mat());
            mesh.ZUp = false;
            return mesh;
        }

        byte[] ReadUri(string uri)
        {
            try
            {
                if (uri.StartsWith("data:"))
                {
                    int c = uri.IndexOf(',');
                    return c < 0 ? null : Convert.FromBase64String(uri.Substring(c + 1));
                }
                if (dir == null) return null;   // akıştan okunuyor, yan dosyalara erişim yok
                string p = Path.Combine(dir, Uri.UnescapeDataString(uri).Replace('/', '\\'));
                FileInfo fi = new FileInfo(p);
                if (!fi.Exists || fi.Length > Thumb.MaxBytes) return null;
                return File.ReadAllBytes(p);
            }
            catch (Exception) { return null; }
        }

        // 4×4, satır-öncelikli [r*4+c]
        static double[] Identity() { return new double[] { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 }; }

        static double[] Mul(double[] a, double[] b)
        {
            double[] r = new double[16];
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++)
                {
                    double s = 0;
                    for (int k = 0; k < 4; k++) s += a[i * 4 + k] * b[k * 4 + j];
                    r[i * 4 + j] = s;
                }
            return r;
        }

        static double[] NodeMatrix(object nd)
        {
            double[] m = Nums(nd, "matrix");
            if (m != null && m.Length == 16)
            {
                double[] r = new double[16];
                for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) r[i * 4 + j] = m[j * 4 + i];   // sütun-öncelikli
                return r;
            }
            double[] t = Nums(nd, "translation") ?? new double[] { 0, 0, 0 };
            double[] q = Nums(nd, "rotation") ?? new double[] { 0, 0, 0, 1 };
            double[] s = Nums(nd, "scale") ?? new double[] { 1, 1, 1 };
            double x = q[0], y = q[1], z = q[2], w = q[3];
            double[] R = {
                1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
                2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
                2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y) };
            double[] o = new double[16];
            for (int i = 0; i < 3; i++)
            {
                for (int j = 0; j < 3; j++) o[i * 4 + j] = R[i * 3 + j] * s[j];
                o[i * 4 + 3] = t[i];
            }
            o[15] = 1;
            return o;
        }

        void Walk(List<object> nodes, int ni, double[] parent, int depth)
        {
            if (depth > 64 || ni < 0 || ni >= nodes.Count) return;
            object nd = nodes[ni];
            double[] m = Mul(parent, NodeMatrix(nd));
            int mi = Int(nd, "mesh", -1);
            if (mi >= 0) AddMesh(mi, m);
            List<object> ch = Arr(nd, "children");
            if (ch != null)
                foreach (object c in ch) Walk(nodes, (int)(double)c, m, depth + 1);
        }

        static int CompSize(int ct)
        {
            switch (ct) { case 5120: case 5121: return 1; case 5122: case 5123: return 2; default: return 4; }
        }

        static int TypeN(string t)
        {
            switch (t) { case "SCALAR": return 1; case "VEC2": return 2; case "VEC3": return 3; case "VEC4": return 4; case "MAT4": return 16; default: return 1; }
        }

        // Erişimciyi double dizisine oku (count × n)
        double[] Accessor(int ai, out int n)
        {
            n = 0;
            List<object> accs = Arr(js, "accessors");
            if (accs == null || ai < 0 || ai >= accs.Count) return null;
            object a = accs[ai];
            int ct = Int(a, "componentType", 5126);
            n = TypeN(Get(a, "type") as string);
            int cnt = Int(a, "count", 0);
            bool norm = Get(a, "normalized") is bool && (bool)Get(a, "normalized");
            double[] r = new double[(long)cnt * n];
            int bvi = Int(a, "bufferView", -1);
            if (bvi < 0) return r;
            List<object> views = Arr(js, "bufferViews");
            object bv = views[bvi];
            byte[] buf = buffers[Int(bv, "buffer", 0)];
            int isz = CompSize(ct);
            int stride = Int(bv, "byteStride", 0);
            if (stride == 0) stride = isz * n;
            int baseOff = Int(bv, "byteOffset", 0) + Int(a, "byteOffset", 0);
            for (int i = 0; i < cnt; i++)
            {
                int o = baseOff + i * stride;
                for (int k = 0; k < n; k++)
                {
                    int p = o + k * isz;
                    if (p + isz > buf.Length) return r;
                    double v;
                    switch (ct)
                    {
                        case 5120: v = (sbyte)buf[p]; if (norm) v = Math.Max(v / 127.0, -1); break;
                        case 5121: v = buf[p]; if (norm) v /= 255.0; break;
                        case 5122: v = BitConverter.ToInt16(buf, p); if (norm) v = Math.Max(v / 32767.0, -1); break;
                        case 5123: v = BitConverter.ToUInt16(buf, p); if (norm) v /= 65535.0; break;
                        case 5125: v = BitConverter.ToUInt32(buf, p); break;
                        default: v = BitConverter.ToSingle(buf, p); break;
                    }
                    r[i * n + k] = v;
                }
            }
            return r;
        }

        int MaterialFor(int mi)
        {
            int idx;
            if (matIndex.TryGetValue(mi, out idx)) return idx;
            Mat m = new Mat();
            List<object> mats = Arr(js, "materials");
            if (mi >= 0 && mats != null && mi < mats.Count)
            {
                object mat = mats[mi];
                object pbr = Get(mat, "pbrMetallicRoughness");
                double[] f = Nums(pbr, "baseColorFactor");
                object bct = Get(pbr, "baseColorTexture");
                if (bct == null)
                {
                    object sg = Get(Get(mat, "extensions"), "KHR_materials_pbrSpecularGlossiness");
                    if (sg != null) { f = Nums(sg, "diffuseFactor") ?? f; bct = Get(sg, "diffuseTexture"); }
                }
                if (f != null && f.Length >= 3) { m.R = (float)f[0]; m.G = (float)f[1]; m.B = (float)f[2]; }
                else { m.R = m.G = m.B = 1f; }
                if (bct != null) LoadTexture(Int(bct, "index", 0), m);
            }
            idx = mesh.Mats.Count;
            mesh.Mats.Add(m);
            matIndex[mi] = idx;
            return idx;
        }

        void LoadTexture(int ti, Mat m)
        {
            Mat cached;
            if (texCache.TryGetValue(ti, out cached))
            {
                if (cached != null) { m.Tex = cached.Tex; m.TW = cached.TW; m.TH = cached.TH; }
                return;
            }
            texCache[ti] = null;
            try
            {
                List<object> texs = Arr(js, "textures"), imgs = Arr(js, "images");
                if (texs == null || imgs == null || ti >= texs.Count) return;
                int src = Int(texs[ti], "source", -1);
                if (src < 0 || src >= imgs.Count) return;
                object im = imgs[src];
                byte[] raw = null;
                int bvi = Int(im, "bufferView", -1);
                if (bvi >= 0)
                {
                    object bv = Arr(js, "bufferViews")[bvi];
                    byte[] buf = buffers[Int(bv, "buffer", 0)];
                    int o = Int(bv, "byteOffset", 0), ln = Int(bv, "byteLength", 0);
                    if (o + ln > buf.Length) return;
                    raw = new byte[ln];
                    Buffer.BlockCopy(buf, o, raw, 0, ln);
                }
                else
                {
                    string uri = Get(im, "uri") as string;
                    if (uri != null) raw = ReadUri(uri);
                }
                if (raw == null) return;
                using (MemoryStream ms = new MemoryStream(raw))
                using (Image img = Image.FromStream(ms, false, false))
                {
                    // Küçük resim için küçültülmüş kopya yeter (Gezgin belleği)
                    int w = img.Width, h = img.Height;
                    double k = Math.Min(1.0, 512.0 / Math.Max(w, h));
                    w = Math.Max(1, (int)(w * k)); h = Math.Max(1, (int)(h * k));
                    using (Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb))
                    {
                        using (Graphics g = Graphics.FromImage(bmp))
                        {
                            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBilinear;
                            g.DrawImage(img, 0, 0, w, h);
                        }
                        BitmapData bd = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                        int[] px = new int[w * h];
                        for (int y = 0; y < h; y++)
                            Marshal.Copy(new IntPtr(bd.Scan0.ToInt64() + (long)y * bd.Stride), px, y * w, w);
                        bmp.UnlockBits(bd);
                        Mat t = new Mat();
                        t.Tex = px; t.TW = w; t.TH = h;
                        texCache[ti] = t;
                        m.Tex = px; m.TW = w; m.TH = h;
                    }
                }
            }
            catch (Exception) { }
        }

        void AddMesh(int mi, double[] T)
        {
            List<object> meshes = Arr(js, "meshes");
            if (meshes == null || mi < 0 || mi >= meshes.Count) return;
            List<object> prims = Arr(meshes[mi], "primitives");
            if (prims == null) return;
            foreach (object prim in prims)
            {
                int mode = Int(prim, "mode", 4);
                object at = Get(prim, "attributes");
                int pa = Int(at, "POSITION", -1);
                if (pa < 0 || (mode != 4 && mode != 5 && mode != 6)) continue;
                int pn, un = 0, cn = 0;
                double[] pos = Accessor(pa, out pn);
                if (pos == null || pn < 3) continue;
                int nv = pos.Length / pn;
                int ia = Int(prim, "indices", -1);
                int[] idx;
                if (ia >= 0)
                {
                    int inn;
                    double[] ii = Accessor(ia, out inn);
                    idx = new int[ii.Length];
                    for (int i = 0; i < ii.Length; i++) idx[i] = (int)ii[i];
                }
                else
                {
                    idx = new int[nv];
                    for (int i = 0; i < nv; i++) idx[i] = i;
                }
                if (mode == 5)
                {
                    List<int> t = new List<int>();
                    for (int k = 0; k + 2 < idx.Length; k++)
                        if (k % 2 == 0) { t.Add(idx[k]); t.Add(idx[k + 1]); t.Add(idx[k + 2]); }
                        else { t.Add(idx[k + 1]); t.Add(idx[k]); t.Add(idx[k + 2]); }
                    idx = t.ToArray();
                }
                else if (mode == 6)
                {
                    List<int> t = new List<int>();
                    for (int k = 1; k + 1 < idx.Length; k++) { t.Add(idx[0]); t.Add(idx[k]); t.Add(idx[k + 1]); }
                    idx = t.ToArray();
                }
                int matI = MaterialFor(Int(prim, "material", -1));
                Mat mat = mesh.Mats[matI];
                double[] uv = null, col = null;
                if (mat.Tex != null && Int(at, "TEXCOORD_0", -1) >= 0) uv = Accessor(Int(at, "TEXCOORD_0", -1), out un);
                if (Int(at, "COLOR_0", -1) >= 0) col = Accessor(Int(at, "COLOR_0", -1), out cn);
                if (uv != null) anyUv = true;
                if (col != null) anyColor = true;
                int ntri = idx.Length / 3;
                for (int f = 0; f < ntri; f++)
                {
                    for (int v = 0; v < 3; v++)
                    {
                        int q = Loader.Clamp(idx[f * 3 + v], nv);
                        double x = pos[q * pn], y = pos[q * pn + 1], z = pos[q * pn + 2];
                        P.Add((float)(T[0] * x + T[1] * y + T[2] * z + T[3]));
                        P.Add((float)(T[4] * x + T[5] * y + T[6] * z + T[7]));
                        P.Add((float)(T[8] * x + T[9] * y + T[10] * z + T[11]));
                        if (uv != null && q * un + 1 < uv.Length) { UV.Add((float)uv[q * un]); UV.Add((float)uv[q * un + 1]); }
                        else { UV.Add(0); UV.Add(0); }
                        if (col != null && q * cn + 2 < col.Length) { C.Add((float)col[q * cn]); C.Add((float)col[q * cn + 1]); C.Add((float)col[q * cn + 2]); }
                        else { C.Add(1); C.Add(1); C.Add(1); }
                    }
                    // Dokusu okunamayan üçgenler malzeme rengini kullanır
                    M.Add(uv != null ? matI : -1 - matI);
                }
            }
        }
    }

    // ------------------------------------------------------------------ çizim (z-tamponlu, 2x örnekleme)
    static class Renderer
    {
        public static int[] Render(Mesh mesh, int size)
        {
            float[] t = mesh.P;
            bool zUp = mesh.ZUp;
            int n = t.Length / 9;
            // Y-yukarıya çevir + sınırlar
            float[] p = t;   // bellek için yerinde dönüştürülür (Gezgin işleminde çalışıyoruz)
            double minX = double.MaxValue, minY = double.MaxValue, minZ = double.MaxValue;
            double maxX = double.MinValue, maxY = double.MinValue, maxZ = double.MinValue;
            for (int i = 0; i + 2 < t.Length; i += 3)
            {
                double x = t[i], y = zUp ? t[i + 2] : t[i + 1], z = zUp ? -t[i + 1] : t[i + 2];
                if (double.IsNaN(x) || double.IsNaN(y) || double.IsNaN(z) || double.IsInfinity(x) || double.IsInfinity(y) || double.IsInfinity(z)) { x = y = z = 0; }
                p[i] = (float)x; p[i + 1] = (float)y; p[i + 2] = (float)z;
                if (x < minX) minX = x; if (x > maxX) maxX = x;
                if (y < minY) minY = y; if (y > maxY) maxY = y;
                if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
            }
            double cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
            // gamma uygulamasındaki küçük resimle aynı açı
            double yaw = -35 * Math.PI / 180, pitch = 25 * Math.PI / 180;
            double cyw = Math.Cos(yaw), syw = Math.Sin(yaw), cp = Math.Cos(pitch), sp = Math.Sin(pitch);
            double ext = 1e-9;
            for (int i = 0; i + 2 < p.Length; i += 3)
            {
                double x = p[i] - cx, y = p[i + 1] - cy, z = p[i + 2] - cz;
                double x1 = cyw * x + syw * z, z1 = -syw * x + cyw * z;
                double y2 = cp * y - sp * z1, z2 = sp * y + cp * z1;
                p[i] = (float)x1; p[i + 1] = (float)y2; p[i + 2] = (float)z2;
                ext = Math.Max(ext, Math.Max(Math.Abs(x1), Math.Abs(y2)));
            }
            const int SS = 2;
            int W = size * SS;
            double sc = 0.92 * W / (2 * ext);
            float[] zb = new float[W * W];
            int[] cb = new int[W * W];
            for (int i = 0; i < zb.Length; i++) zb[i] = float.NegativeInfinity;
            double lx = 0.35, ly = 0.55, lz = 0.75, ll = Math.Sqrt(lx * lx + ly * ly + lz * lz);
            lx /= ll; ly /= ll; lz /= ll;
            float[] C = mesh.C, UV = mesh.UV;
            int[] TM = mesh.M;
            for (int f = 0; f < n; f++)
            {
                int o = f * 9;
                double ax = p[o], ay = p[o + 1], az = p[o + 2];
                double bx = p[o + 3], by = p[o + 4], bz = p[o + 5];
                double qx = p[o + 6], qy = p[o + 7], qz = p[o + 8];
                double ux = bx - ax, uy = by - ay, uz = bz - az, vx = qx - ax, vy = qy - ay, vz = qz - az;
                double nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
                double nl = Math.Sqrt(nx * nx + ny * ny + nz * nz);
                if (nl <= 0) continue;
                nx /= nl; ny /= nl; nz /= nl;
                double shade = 0.30 + 0.55 * Math.Abs(nx * lx + ny * ly + nz * lz) + 0.22 * Math.Abs(nz);
                // malzeme
                int mi = TM != null ? TM[f] : 0;
                bool useTex = mi >= 0;
                if (mi < 0) mi = -1 - mi;
                Mat mat = mesh.Mats[mi < mesh.Mats.Count ? mi : 0];
                int[] tex = useTex && UV != null ? mat.Tex : null;
                double mr = mat.R * shade, mg = mat.G * shade, mb = mat.B * shade;
                bool perPixel = tex != null || C != null;
                int flat = Pack(mr, mg, mb);

                double X0 = ax * sc + W / 2.0, Y0 = -ay * sc + W / 2.0;
                double X1 = bx * sc + W / 2.0, Y1 = -by * sc + W / 2.0;
                double X2 = qx * sc + W / 2.0, Y2 = -qy * sc + W / 2.0;
                int x0 = Math.Max(0, (int)Math.Floor(Math.Min(X0, Math.Min(X1, X2))));
                int x1 = Math.Min(W - 1, (int)Math.Ceiling(Math.Max(X0, Math.Max(X1, X2))));
                int y0 = Math.Max(0, (int)Math.Floor(Math.Min(Y0, Math.Min(Y1, Y2))));
                int y1 = Math.Min(W - 1, (int)Math.Ceiling(Math.Max(Y0, Math.Max(Y1, Y2))));
                if (x0 > x1 || y0 > y1) continue;
                double den = (Y1 - Y2) * (X0 - X2) + (X2 - X1) * (Y0 - Y2);
                if (Math.Abs(den) < 1e-12)
                {
                    // çok küçük üçgen: tek piksel
                    int px = (int)X0, py = (int)Y0;
                    if (px >= 0 && py >= 0 && px < W && py < W && az > zb[py * W + px])
                    {
                        zb[py * W + px] = (float)az;
                        cb[py * W + px] = perPixel ? Shade(mesh, f, 1, 0, 0, tex, mat, mr, mg, mb) : flat;
                    }
                    continue;
                }
                for (int y = y0; y <= y1; y++)
                {
                    double Py = y + 0.5;
                    for (int x = x0; x <= x1; x++)
                    {
                        double Px = x + 0.5;
                        double l1 = ((Y1 - Y2) * (Px - X2) + (X2 - X1) * (Py - Y2)) / den;
                        double l2 = ((Y2 - Y0) * (Px - X2) + (X0 - X2) * (Py - Y2)) / den;
                        double l3 = 1 - l1 - l2;
                        if (l1 < -1e-6 || l2 < -1e-6 || l3 < -1e-6) continue;
                        float z = (float)(l1 * az + l2 * bz + l3 * qz);
                        int k = y * W + x;
                        if (z > zb[k])
                        {
                            zb[k] = z;
                            cb[k] = perPixel ? Shade(mesh, f, l1, l2, l3, tex, mat, mr, mg, mb) : flat;
                        }
                    }
                }
            }
            // 2x2 küçült; kaplama = alfa (önceden çarpılmış ARGB)
            int[] outp = new int[size * size];
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    int r = 0, gg = 0, bb = 0, a = 0;
                    for (int dy = 0; dy < SS; dy++)
                        for (int dx = 0; dx < SS; dx++)
                        {
                            int k = (y * SS + dy) * W + x * SS + dx;
                            if (float.IsNegativeInfinity(zb[k])) continue;
                            int c = cb[k];
                            r += (c >> 16) & 255; gg += (c >> 8) & 255; bb += c & 255; a += 255;
                        }
                    int q = SS * SS;
                    outp[y * size + x] = ((a / q) << 24) | ((r / q) << 16) | ((gg / q) << 8) | (bb / q);
                }
            return outp;
        }

        static int Pack(double r, double g, double b)
        {
            int R = (int)Math.Max(0, Math.Min(255, r * 255));
            int G = (int)Math.Max(0, Math.Min(255, g * 255));
            int B = (int)Math.Max(0, Math.Min(255, b * 255));
            return (R << 16) | (G << 8) | B;
        }

        static int Shade(Mesh m, int f, double l1, double l2, double l3, int[] tex, Mat mat, double r, double g, double b)
        {
            if (m.C != null)
            {
                int o = f * 9;
                float[] C = m.C;
                r *= l1 * C[o] + l2 * C[o + 3] + l3 * C[o + 6];
                g *= l1 * C[o + 1] + l2 * C[o + 4] + l3 * C[o + 7];
                b *= l1 * C[o + 2] + l2 * C[o + 5] + l3 * C[o + 8];
            }
            if (tex != null)
            {
                int o = f * 6;
                float[] U = m.UV;
                double u = l1 * U[o] + l2 * U[o + 2] + l3 * U[o + 4];
                double v = l1 * U[o + 1] + l2 * U[o + 3] + l3 * U[o + 5];
                u -= Math.Floor(u); v -= Math.Floor(v);
                int tx = Math.Min(mat.TW - 1, (int)(u * mat.TW)), ty = Math.Min(mat.TH - 1, (int)(v * mat.TH));
                int c = tex[ty * mat.TW + tx];
                r *= ((c >> 16) & 255) / 255.0; g *= ((c >> 8) & 255) / 255.0; b *= (c & 255) / 255.0;
            }
            return Pack(r, g, b);
        }
    }

    // ------------------------------------------------------------------ HBITMAP
    static class Dib
    {
        [StructLayout(LayoutKind.Sequential)]
        struct BITMAPINFOHEADER
        {
            public int biSize, biWidth, biHeight;
            public short biPlanes, biBitCount;
            public int biCompression, biSizeImage, biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant;
        }

        [DllImport("gdi32.dll")]
        static extern IntPtr CreateDIBSection(IntPtr hdc, ref BITMAPINFOHEADER bmi, uint usage, out IntPtr bits, IntPtr hSection, uint offset);

        public static IntPtr Create(int[] px, int w, int h)
        {
            BITMAPINFOHEADER bi = new BITMAPINFOHEADER();
            bi.biSize = Marshal.SizeOf(typeof(BITMAPINFOHEADER));
            bi.biWidth = w;
            bi.biHeight = -h;   // yukarıdan aşağı
            bi.biPlanes = 1;
            bi.biBitCount = 32;
            IntPtr bits;
            IntPtr hbmp = CreateDIBSection(IntPtr.Zero, ref bi, 0, out bits, IntPtr.Zero, 0);
            if (hbmp != IntPtr.Zero && bits != IntPtr.Zero) Marshal.Copy(px, 0, bits, px.Length);
            return hbmp;
        }
    }
}
