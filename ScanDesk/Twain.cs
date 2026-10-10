using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ScanDesk
{
    [StructLayout(LayoutKind.Sequential, Pack = 2, CharSet = CharSet.Ansi)]
    internal struct TwVersion
    {
        public ushort Major, Minor, Language, Country;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 34)] public string Info;
    }
    [StructLayout(LayoutKind.Sequential, Pack = 2, CharSet = CharSet.Ansi)]
    internal struct TwIdentity
    {
        public uint Id;
        public TwVersion Version;
        public ushort ProtocolMajor, ProtocolMinor;
        public uint Groups;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 34)] public string Manufacturer;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 34)] public string Family;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 34)] public string Name;
        public override string ToString() { return Name; }
    }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwUi { public ushort Show, Modal; public IntPtr Parent; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwCap { public ushort Id, ContainerType; public IntPtr Handle; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwEvent { public IntPtr NativeMessage; public ushort Message; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwPending { public ushort Count; public uint Reserved; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwMemory { public uint Flags, Length; public IntPtr Pointer; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwImageMem
    {
        public ushort Compression;
        public uint BytesPerRow, Columns, Rows, XOffset, YOffset, BytesWritten;
        public TwMemory Memory;
    }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwSetupMem { public uint Minimum, Maximum, Preferred; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwStatus { public ushort Condition, Reserved; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwFix { public short Whole; public ushort Fraction; public float Value { get { return Whole + Fraction / 65536f; } } }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwFrame
    {
        public TwFix Left, Top, Right, Bottom;
        internal static TwFix Fixed(double value)
        {
            if (double.IsNaN(value) || double.IsInfinity(value) || value < 0 || value >= 32767) throw new ArgumentOutOfRangeException("value");
            long raw = (long)Math.Round(value * 65536);
            return new TwFix { Whole = checked((short)(raw >> 16)), Fraction = (ushort)(raw & 65535) };
        }
        internal static TwFrame Inches(double left, double top, double right, double bottom)
        {
            if (right <= left || bottom <= top) throw new ArgumentException("The scan rectangle must have a positive width and height.");
            return new TwFrame { Left = Fixed(left), Top = Fixed(top), Right = Fixed(right), Bottom = Fixed(bottom) };
        }
        public override string ToString()
        {
            return string.Format(System.Globalization.CultureInfo.InvariantCulture, "({0:F5}, {1:F5}) - ({2:F5}, {3:F5}) inches", Left.Value, Top.Value, Right.Value, Bottom.Value);
        }
    }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwLayout { public TwFrame Frame; public uint DocumentNumber, PageNumber, FrameNumber; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    internal struct TwImageInfo
    {
        public TwFix X, Y;
        public int Width, Height;
        public short Samples;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)] public short[] Bits;
        public short BitsPerPixel;
        public ushort Planar;
        public short PixelType;
        public ushort Compression;
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct NativeMessage
    {
        public IntPtr Hwnd;
        public uint Message;
        public IntPtr WParam, LParam;
        public uint Time;
        public int X, Y;
    }

    internal sealed class Twain : IMessageFilter, IDisposable
    {
        [DllImport("twain_32.dll", EntryPoint = "DSM_Entry", CharSet = CharSet.Ansi, ExactSpelling = true)]
        private static extern ushort Entry(ref TwIdentity origin, IntPtr destination, uint group, ushort dat, ushort message, IntPtr data);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalLock(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalFree(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern UIntPtr GlobalSize(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalAlloc(uint flags, UIntPtr size);
        [DllImport("user32.dll")] private static extern uint GetMessageTime();
        [DllImport("user32.dll")] private static extern uint GetMessagePos();
        private TwIdentity app;
        private IntPtr source;
        private readonly Form owner;
        private readonly int resolutionDpi;
        private bool managerOpen, sourceOpen, enabled, transferReady, transferScheduled, filterAdded;
        private bool hidden;
        private TwFrame hiddenFrame;
        public event Action<string> Diagnostic;
        public event Action<Page> Frame;
        public event Action<Exception> Failed;
        public event Action Finished;
        public string Folder;
        private void Trace(string message) { if (Diagnostic != null) Diagnostic(message); }
        public Twain(Form owner, int dpi = FilmPreset.Dpi)
        {
            FilmPreset.CheckResolution(dpi); this.owner = owner; resolutionDpi = dpi;
            app = new TwIdentity { Version = new TwVersion { Major = 0, Minor = 1, Language = 13, Country = 1, Info = "FilmDesk prototype" }, ProtocolMajor = 1, ProtocolMinor = 9, Groups = 3, Manufacturer = "Personal project", Family = "35mm film", Name = "FilmDesk" };
            IntPtr parent = owner.Handle;
            Check(Call(1, 4, 0x301, ref parent, false), "Open TWAIN manager"); managerOpen = true;
        }
        private ushort Call<T>(uint group, ushort dat, ushort message, ref T value, bool toSource) where T : struct
        {
            IntPtr memory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(T)));
            try
            {
                Marshal.StructureToPtr(value, memory, false);
                ushort result = Entry(ref app, toSource ? source : IntPtr.Zero, group, dat, message, memory);
                value = (T)Marshal.PtrToStructure(memory, typeof(T));
                return result;
            }
            finally { Marshal.FreeHGlobal(memory); }
        }
        private void Check(ushort result, string operation)
        {
            if (result == 0) return;
            var status = new TwStatus();
            ushort statusResult = Call(1, 8, 1, ref status, sourceOpen);
            throw new InvalidOperationException(operation + " failed (TWAIN result " + result + (statusResult == 0 ? ", condition " + status.Condition : "") + "). Close other scanner software and check the scanner connection.");
        }
        public List<TwIdentity> Discover()
        {
            var result = new List<TwIdentity>(); var identity = new TwIdentity();
            ushort rc = Call(1, 3, 4, ref identity, false);
            while (rc == 0)
            {
                result.Add(identity); identity = new TwIdentity(); rc = Call(1, 3, 5, ref identity, false);
            }
            if (rc != 7) Check(rc, "List TWAIN scanners");
            return result;
        }
        public void Open(TwIdentity identity)
        {
            if (sourceOpen) throw new InvalidOperationException("A TWAIN source is already open.");
            Check(Call(1, 3, 0x401, ref identity, false), "Open " + identity.Name);
            source = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(TwIdentity)));
            Marshal.StructureToPtr(identity, source, false); sourceOpen = true;
        }
        public bool SetValue(ushort capability, ushort value)
        {
            return SetOneValue(capability, 4, value);
        }
        public bool SetResolution(ushort capability, short dpi)
        {
            return SetOneValue(capability, 7, unchecked((uint)(ushort)dpi));
        }
        private bool SetOneValue(ushort capability, ushort type, uint value)
        {
            var cap = new TwCap { Id = capability, ContainerType = 5, Handle = GlobalAlloc(0x42, (UIntPtr)6) };
            if (cap.Handle == IntPtr.Zero) throw new OutOfMemoryException();
            IntPtr ptr = GlobalLock(cap.Handle);
            if (ptr == IntPtr.Zero) { GlobalFree(cap.Handle); throw new OutOfMemoryException(); }
            try { Marshal.WriteInt16(ptr, unchecked((short)type)); Marshal.WriteInt32(ptr, 2, unchecked((int)value)); }
            finally { GlobalUnlock(cap.Handle); }
            try { return Call(1, 1, 6, ref cap, true) == 0; }
            finally { GlobalFree(cap.Handle); }
        }
        public string GetValue(ushort capability)
        {
            var cap = new TwCap { Id = capability };
            ushort result = Call(1, 1, 2, ref cap, true);
            if (result != 0) { if (cap.Handle != IntPtr.Zero) GlobalFree(cap.Handle); return "unsupported (" + result + ")"; }
            IntPtr ptr = GlobalLock(cap.Handle);
            try
            {
                if (ptr == IntPtr.Zero) throw new InvalidOperationException("Cannot read TWAIN capability.");
                if (cap.ContainerType == 5) return "type=" + Marshal.ReadInt16(ptr) + ", value=" + Marshal.ReadInt32(ptr, 2);
                return "container=" + cap.ContainerType;
            }
            finally { if (ptr != IntPtr.Zero) GlobalUnlock(cap.Handle); GlobalFree(cap.Handle); }
        }
        public void Enable()
        {
            if (!sourceOpen) throw new InvalidOperationException("Select a TWAIN source first.");
            if (!SetValue(0x0103, 2) || GetValue(0x0103) != "type=4, value=2") throw new InvalidOperationException("The driver did not accept buffered memory transfer, required to preserve 48-bit film samples.");
            if (!SetValue(0x111e, 1) || GetValue(0x111e) != "type=4, value=1")
                throw new InvalidOperationException("The driver did not accept the film (transmissive) light path. FilmDesk will not start a paper scan.");
            // Request standard settings. Canon's screen remains authoritative and transfer metadata is checked.
            SetValue(0x0101, 2); SetValue(0x112b, 16);
            SetResolution(0x1118, (short)resolutionDpi); SetResolution(0x1119, (short)resolutionDpi);
            // ScanGear owns positive/negative subtype, frame selection, corrections, scale and Quiet Mode.
            // Transmissive light alone does not select negative/positive subtype.
            Application.AddMessageFilter(this); filterAdded = true;
            var ui = new TwUi { Show = 1, Modal = 0, Parent = owner.Handle };
            enabled = true; // Receive messages that a driver may send while enabling.
            try { Check(Call(1, 9, 0x502, ref ui, true), "Open Canon ScanGear"); }
            catch { enabled = false; Application.RemoveMessageFilter(this); filterAdded = false; throw; }
        }
        // Experimental acquisition path: a caller must first inspect Canon's persisted
        // Quiet Mode and preservation settings. This does not claim control of private settings.
        public TwLayout PrepareHidden(TwFrame frame)
        {
            if (!sourceOpen || enabled) throw new InvalidOperationException("Open an idle TWAIN source first.");
            hiddenFrame = new TwFrame();
            if (GetValue(0x100e) != "type=6, value=1") throw new InvalidOperationException("The driver does not report support for a hidden scanning interface.");
            Require(0x0103, 2, "buffered memory transfer");
            Require(0x111e, 1, "transmissive film light path");
            Require(0x0102, 0, "inches");
            if (!SetValue(0x0101, 2) || !SetValue(0x112b, 16)) throw new InvalidOperationException("The driver rejected the 48-bit RGB request.");
            if (!SetResolution(0x1118, (short)resolutionDpi) || !SetResolution(0x1119, (short)resolutionDpi)) throw new InvalidOperationException("The driver rejected the requested film DPI.");
            Trace("Before enable: RGB=" + GetValue(0x0101) + "; bit depth=" + GetValue(0x112b) + "; X DPI=" + GetValue(0x1118) + "; Y DPI=" + GetValue(0x1119));
            Trace("Automatic brightness: " + GetValue(0x1100) + "; X scaling: " + GetValue(0x1124) + "; Y scaling: " + GetValue(0x1125));
            var layout = new TwLayout();
            Check(Call(2, 0x102, 1, ref layout, true), "Read scan-area coordinates");
            Trace("Original layout: " + layout.Frame);
            layout.Frame = frame;
            Check(Call(2, 0x102, 6, ref layout, true), "Set scan-area coordinates");
            Check(Call(2, 0x102, 1, ref layout, true), "Read back scan-area coordinates");
            Trace("Requested layout: " + frame + "; readback: " + layout.Frame);
            const double tolerance = 1.0 / 4800;
            if (Math.Abs(layout.Frame.Left.Value - frame.Left.Value) > tolerance || Math.Abs(layout.Frame.Top.Value - frame.Top.Value) > tolerance || Math.Abs(layout.Frame.Right.Value - frame.Right.Value) > tolerance || Math.Abs(layout.Frame.Bottom.Value - frame.Bottom.Value) > tolerance)
                throw new InvalidOperationException("Canon changed the requested scan rectangle; acquisition was not started.");
            hiddenFrame = frame;
            return layout;
        }
        private void Require(ushort capability, ushort value, string name)
        {
            if (!SetValue(capability, value) || GetValue(capability) != "type=4, value=" + value)
                throw new InvalidOperationException("The driver did not accept " + name + ". Acquisition was not started.");
        }
        public void EnableHidden()
        {
            if (!sourceOpen || enabled || hiddenFrame.Right.Value <= hiddenFrame.Left.Value) throw new InvalidOperationException("Prepare a verified scan rectangle first.");
            hidden = true;
            Application.AddMessageFilter(this); filterAdded = true;
            var ui = new TwUi { Show = 0, Modal = 0, Parent = owner.Handle };
            enabled = true;
            Trace("Enabling the source with ShowUI=FALSE. No preview was requested.");
            try { Check(Call(1, 9, 0x502, ref ui, true), "Start film scan with Canon's window hidden"); }
            catch { Dispose(); throw; }
            Trace("Hidden enable returned successfully.");
        }
        public bool PreFilterMessage(ref Message message)
        {
            if (!enabled || !sourceOpen) return false;
            uint position = GetMessagePos();
            var native = new NativeMessage { Hwnd = message.HWnd, Message = (uint)message.Msg, WParam = message.WParam, LParam = message.LParam, Time = GetMessageTime(), X = unchecked((short)(position & 0xffff)), Y = unchecked((short)(position >> 16)) };
            IntPtr memory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(NativeMessage)));
            try
            {
                Marshal.StructureToPtr(native, memory, false);
                var evt = new TwEvent { NativeMessage = memory };
                ushort rc = Call(1, 2, 0x601, ref evt, true);
                if (evt.Message == 0x101 && !transferScheduled)
                {
                    transferReady = true; transferScheduled = true;
                    owner.BeginInvoke((Action)Transfer);
                }
                else if (evt.Message == 0x102 || evt.Message == 0x103)
                    owner.BeginInvoke((Action)delegate { if (enabled) Finish(); });
                return rc == 4;
            }
            catch (Exception ex) { owner.BeginInvoke((Action)delegate { Fail(ex); }); return false; }
            finally { Marshal.FreeHGlobal(memory); }
        }
        private void Transfer()
        {
            if (!enabled || !sourceOpen) return;
            try
            {
                ushort remaining;
                do
                {
                    var info = new TwImageInfo { Bits = new short[8] };
                    Check(Call(2, 0x101, 1, ref info, true), "Read film frame information");
                    Trace("Received image info: " + info.Width + " x " + info.Height + "; " + info.X.Value + " x " + info.Y.Value + " dpi; " + info.BitsPerPixel + " bits; " + info.Samples + " samples; pixel type=" + info.PixelType);
                    FilmPreset.Validate(info, resolutionDpi);
                    if (hidden && (Math.Abs(info.Width - Math.Round((hiddenFrame.Right.Value - hiddenFrame.Left.Value) * resolutionDpi)) > 3 || Math.Abs(info.Height - Math.Round((hiddenFrame.Bottom.Value - hiddenFrame.Top.Value) * resolutionDpi)) > 3))
                        throw new InvalidOperationException("The acquired dimensions do not match our scan rectangle. No TIFF was published.");
                    var pending = new TwPending();
                    Page received = ReceiveMemory(info);
                    Check(Call(1, 5, 0x701, ref pending, true), "Finish frame transfer");
                    transferReady = pending.Count != 0; remaining = pending.Count;
                    if (received != null)
                    {
                        if (Frame != null) Frame(received);
                    }
                    else { Finish(); return; }
                } while (remaining != 0);
                transferScheduled = false;
                if (hidden) { Finish(); return; }
                // Keep ScanGear open for another strip or close it with its Close button.
            }
            catch (Exception ex) { Fail(ex); }
        }
        private Page ReceiveMemory(TwImageInfo info)
        {
            var setup = new TwSetupMem();
            Check(Call(1, 6, 1, ref setup, true), "Read film transfer buffer size");
            uint required = checked((uint)info.Width * 6);
            uint length = Math.Max(setup.Minimum, Math.Max(required, Math.Min(setup.Preferred, 8 * 1024 * 1024)));
            if (length > 64 * 1024 * 1024 || (setup.Maximum != 0 && length > setup.Maximum))
                throw new InvalidOperationException("The film driver's transfer buffer limits are unsupported.");
            Directory.CreateDirectory(Folder);
            string path = Path.Combine(Folder, "frame-" + DateTime.Now.ToString("HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".tif");
            IntPtr buffer = Marshal.AllocHGlobal(checked((int)length));
            bool cancelled = false;
            try
            {
                var bytes = new byte[length];
                Export.Atomic(path, delegate(string temp)
                {
                    using (var rows = new FilmRows(temp, info, resolutionDpi))
                    {
                        ushort rc;
                        do
                        {
                            var transfer = new TwImageMem { Memory = new TwMemory { Flags = 9, Length = length, Pointer = buffer } };
                            rc = Call(2, 0x103, 1, ref transfer, true);
                            if (rc == 3) { cancelled = true; throw new OperationCanceledException("Film scan cancelled."); }
                            if (rc != 0 && rc != 6) Check(rc, "Receive 48-bit film samples");
                            if (transfer.BytesWritten > length) throw new InvalidOperationException("The driver exceeded its film transfer buffer.");
                            Marshal.Copy(buffer, bytes, 0, checked((int)transfer.BytesWritten));
                            rows.Append(transfer, bytes);
                        } while (rc != 6);
                        rows.Complete();
                    }
                });
                return Page.Read(path);
            }
            catch (OperationCanceledException) { if (cancelled) return null; throw; }
            finally { Marshal.FreeHGlobal(buffer); }
        }
        internal static Page SaveDib(IntPtr handle, TwImageInfo info, string folder)
        {
            if (handle == IntPtr.Zero) throw new InvalidOperationException("The scanner returned no frame data.");
            ulong length = GlobalSize(handle).ToUInt64();
            if (length < 40 || length > 512 * 1024 * 1024) throw new InvalidOperationException("Unsupported film frame buffer size.");
            IntPtr ptr = GlobalLock(handle);
            if (ptr == IntPtr.Zero) throw new InvalidOperationException("Cannot read the film frame buffer.");
            try
            {
                var header = new byte[40]; Marshal.Copy(ptr, header, 0, header.Length);
                return WriteDib(header, (int)length, info, folder, delegate(Stream stream)
                {
                    var chunk = new byte[65536];
                    for (int offset = 0; offset < (int)length;)
                    {
                        int count = Math.Min(chunk.Length, (int)length - offset);
                        Marshal.Copy(IntPtr.Add(ptr, offset), chunk, 0, count);
                        stream.Write(chunk, 0, count); offset += count;
                    }
                });
            }
            finally { GlobalUnlock(handle); }
        }
        internal static Page SaveDibBytes(byte[] dib, TwImageInfo info, string folder)
        {
            return CompleteDib(WriteDib(dib, dib.Length, info, folder, delegate(Stream stream) { stream.Write(dib, 0, dib.Length); }));
        }
        private static Page WriteDib(byte[] dib, int length, TwImageInfo info, string folder, Action<Stream> writePixels)
        {
            if (dib.Length < 40) throw new InvalidOperationException("Truncated DIB header.");
            int header = BitConverter.ToInt32(dib, 0); ushort bits = BitConverter.ToUInt16(dib, 14);
            int compression = BitConverter.ToInt32(dib, 16), colors = BitConverter.ToInt32(dib, 32);
            if (header < 40 || header > length || colors < 0 || (bits != 8 && bits != 24 && bits != 32) || (compression != 0 && compression != 3))
                throw new InvalidOperationException("Unsupported native film frame encoding.");
            if (colors == 0 && bits <= 8) colors = 1 << bits;
            int offset = checked(14 + header + colors * 4 + (header == 40 && compression == 3 ? 12 : 0));
            if (offset >= length + 14) throw new InvalidOperationException("Truncated DIB pixel data.");
            int width = BitConverter.ToInt32(dib, 4), height = BitConverter.ToInt32(dib, 8);
            if (width != info.Width || Math.Abs((long)height) != info.Height || width <= 0 || info.Height <= 0)
                throw new InvalidOperationException("Transferred frame dimensions do not match the driver metadata.");
            long stride = ((long)width * bits + 31) / 32 * 4;
            if ((long)offset - 14 + stride * info.Height > length) throw new InvalidOperationException("Truncated DIB pixel data.");
            float x = info.X.Value, y = info.Y.Value;
            if (x <= 0 || y <= 0) throw new InvalidOperationException("The film driver returned invalid DPI metadata.");
            Directory.CreateDirectory(folder);
            string path = Path.Combine(folder, "frame-" + DateTime.Now.ToString("HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".bmp");
            using (var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write))
            using (var writer = new BinaryWriter(stream))
            {
                writer.Write((ushort)0x4d42); writer.Write(checked(14 + length)); writer.Write(0); writer.Write(offset); writer.Flush();
                writePixels(stream);
                stream.Position = 14 + 24; writer.Write((int)Math.Round(x / 0.0254)); writer.Write((int)Math.Round(y / 0.0254));
            }
            return new Page { Path = path, Width = width, Height = info.Height, DpiX = x, DpiY = y };
        }
        internal static Page CompleteDib(Page native)
        {
            string path = Path.ChangeExtension(native.Path, ".tif");
            try
            {
                Export.Atomic(path, delegate(string temp)
                {
                    using (var bitmap = (Bitmap)Image.FromFile(native.Path))
                    { bitmap.SetResolution(native.DpiX, native.DpiY); Export.Tiff(bitmap, temp); }
                });
                Page page = Page.Read(path);
                File.Delete(native.Path); return page;
            }
            catch (Exception ex) { throw new InvalidOperationException("TIFF conversion failed. The received scan is preserved for recovery at " + native.Path, ex); }
        }
        private void Fail(Exception ex)
        {
            try { Dispose(); } finally { if (Failed != null) Failed(ex); if (Finished != null) Finished(); }
        }
        private void Finish() { Dispose(); if (Finished != null) Finished(); }
        public void Dispose()
        {
            if (filterAdded) { Application.RemoveMessageFilter(this); filterAdded = false; }
            try
            {
                if (sourceOpen && transferReady) { var pending = new TwPending(); Call(1, 5, 7, ref pending, true); transferReady = false; }
                if (enabled) { var ui = new TwUi { Parent = owner.Handle }; Call(1, 9, 0x501, ref ui, true); enabled = false; }
                if (sourceOpen)
                {
                    TwIdentity identity = (TwIdentity)Marshal.PtrToStructure(source, typeof(TwIdentity));
                    Call(1, 3, 0x402, ref identity, false); sourceOpen = false;
                }
                if (managerOpen) { IntPtr parent = owner.Handle; Call(1, 4, 0x302, ref parent, false); managerOpen = false; }
            }
            finally { if (source != IntPtr.Zero) { Marshal.FreeHGlobal(source); source = IntPtr.Zero; } }
        }
    }
}
