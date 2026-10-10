using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using BitMiracle.LibTiff.Classic;

namespace ScanDesk
{
    internal static class Tests
    {
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalAlloc(uint flags, UIntPtr size);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalLock(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr handle);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalFree(IntPtr handle);
        private static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
        public static int Run(string[] args)
        {
            if (args[0] == "--headless-probe" || args[0] == "--headless-scan") return Headless.Run(args);
            string folder = Path.Combine(Program.Root, "test-output"); Directory.CreateDirectory(folder);
            string report = Path.Combine(folder, args[0] == "--probe" ? "scanner-probe.txt" : "self-test.txt");
            var log = new StringBuilder();
            try
            {
                if (args[0] == "--probe")
                {
                    using (var form = new Form())
                    using (var twain = new Twain(form))
                    {
                        var sources = twain.Discover();
                        foreach (TwIdentity item in sources) log.AppendLine(item.Name + " | " + item.Manufacturer + " | driver " + item.Version.Major + "." + item.Version.Minor);
                        var canon = sources.First(s => s.Name.IndexOf("MG8100", StringComparison.OrdinalIgnoreCase) >= 0 && s.Name.IndexOf("WIA", StringComparison.OrdinalIgnoreCase) < 0);
                        twain.Open(canon);
                        log.AppendLine("Connected to " + canon.Name);
                        log.AppendLine("Light path: " + twain.GetValue(0x111e));
                        log.AppendLine("Native transfer mode accepted: " + twain.SetValue(0x0103, 0));
                        log.AppendLine("Custom driver settings: " + twain.GetValue(0x1015));
                        log.AppendLine("UI controllable: " + twain.GetValue(0x100e));
                        bool filmAccepted = twain.SetValue(0x111e, 1);
                        log.AppendLine("Transmissive film light path accepted: " + filmAccepted);
                        log.AppendLine("Film light path readback: " + twain.GetValue(0x111e));
                        Assert(filmAccepted && twain.GetValue(0x111e) == "type=4, value=1", "Canon film source setting");
                        bool memoryAccepted = twain.SetValue(0x0103, 2);
                        log.AppendLine("Buffered memory transfer accepted: " + memoryAccepted + "; readback: " + twain.GetValue(0x0103));
                        Assert(memoryAccepted && twain.GetValue(0x0103) == "type=4, value=2", "Canon buffered transfer setting");
                        log.AppendLine("48-bit RGB requests accepted: RGB=" + twain.SetValue(0x0101, 2) + ", 16 bits/channel=" + twain.SetValue(0x112b, 16));
                        foreach (short dpi in new short[] { 9600, 4800 })
                        {
                            log.AppendLine(dpi + " dpi requests accepted: X=" + twain.SetResolution(0x1118, dpi) + ", Y=" + twain.SetResolution(0x1119, dpi));
                            log.AppendLine("Current bit depth: " + twain.GetValue(0x112b) + "; X DPI: " + twain.GetValue(0x1118) + "; Y DPI: " + twain.GetValue(0x1119));
                        }
                        log.AppendLine("No scan or preview was requested. Film light path set for this TWAIN session.");
                    }
                }
                else if (args[0] == "--self-test")
                {
                    Assert(IntPtr.Size == 4, "Canon TWAIN requires a 32-bit process.");
                    Assert(Marshal.SizeOf(typeof(TwIdentity)) == 156, "TW_IDENTITY ABI size");
                    Assert(Marshal.SizeOf(typeof(TwImageInfo)) == 42, "TW_IMAGEINFO ABI size");
                    Assert(Marshal.SizeOf(typeof(TwUi)) == 8 && Marshal.SizeOf(typeof(TwEvent)) == 6, "TWAIN UI/event ABI sizes");
                    Assert(Marshal.SizeOf(typeof(TwFrame)) == 16 && Marshal.SizeOf(typeof(TwLayout)) == 28, "TWAIN frame/layout ABI sizes");
                    TwFrame frame = TwFrame.Inches(0.1, 8.8, 1.1, 9.05);
                    Assert(Math.Abs(frame.Left.Value - 0.1) < 1.0 / 65536 && Math.Abs(frame.Bottom.Value - 9.05) < 1.0 / 65536, "TWAIN FIX32 preserves fractional scan coordinates");
                    try { TwFrame.Inches(1, 0, 0, 1); throw new Exception("Reversed crop accepted"); } catch (ArgumentException) { }
                    Assert(Marshal.SizeOf(typeof(TwMemory)) == 12 && Marshal.SizeOf(typeof(TwImageMem)) == 38 && Marshal.SizeOf(typeof(TwSetupMem)) == 12, "TWAIN buffered transfer ABI sizes");
                    log.AppendLine("PASS: 32-bit TWAIN structure layouts match the official header.");
                    Test48Bit(folder, log);
                    Test48Bit(folder, log, 9600);
                    TestLarge48Bit(folder, log);
                    string input = Path.Combine(folder, "fixture.tif");
                    using (var image = new Bitmap(120, 80))
                    using (Graphics graphics = Graphics.FromImage(image))
                    {
                        image.SetResolution(2400, 2400); graphics.Clear(Color.White); graphics.FillRectangle(Brushes.Red, 0, 0, 40, 80); graphics.FillRectangle(Brushes.Blue, 80, 0, 40, 80); Export.Tiff(image, input);
                    }
                    Page page = Page.Read(input); page.Rotate();
                    Assert(page.Width == 80 && page.Height == 120 && Math.Abs(page.DpiX - 2400) < 1, "Rotate dimensions/DPI");
                    Assert(File.Exists(input), "Rotation preserves original");
                    Assert(Path.GetExtension(page.Path) == ".tif", "Rotation saves TIFF");
                    foreach (string extension in new[] { ".tif", ".tiff", ".jpg", ".jpeg" })
                    {
                        string destination = Path.Combine(folder, "export" + extension); Export.Image(page, destination);
                        using (Image image = Image.FromFile(destination)) Assert(image.Width == 80 && image.Height == 120 && Math.Abs(image.HorizontalResolution - 2400) < 1, "Export dimensions/DPI " + extension);
                        Export.Image(page, destination); // Exercise atomic replacement of an existing output.
                    }
                    try { Export.Image(page, Path.Combine(folder, "forbidden.png")); throw new Exception("PNG export was accepted"); } catch (InvalidOperationException) { }
                    Assert(!File.Exists(Path.Combine(folder, "forbidden.png")), "PNG export creates no output");
                    log.AppendLine("PASS: TIFF rotation, original preservation, TIFF/JPEG export, PNG rejection, DPI, atomic replacement.");
                    string sentinel = Path.Combine(folder, "atomic.txt"); File.WriteAllText(sentinel, "original");
                    try { Export.Atomic(sentinel, delegate(string temp) { File.WriteAllText(temp, "partial"); throw new IOException("simulated failure"); }); } catch (IOException) { }
                    Assert(File.ReadAllText(sentinel) == "original", "A failed export must not overwrite an existing file.");
                    Assert(!Directory.GetFiles(folder, "*.tmp").Any(), "Failed export temporary file cleanup");
                    log.AppendLine("PASS: failed export preserves existing file and cleans its temporary file.");
                    byte[] dib;
                    using (var image = new Bitmap(2, 2, PixelFormat.Format24bppRgb))
                    using (var stream = new MemoryStream())
                    {
                        image.SetPixel(0, 0, Color.Red); image.SetPixel(1, 1, Color.Blue); image.Save(stream, ImageFormat.Bmp); dib = stream.ToArray().Skip(14).ToArray();
                    }
                    var info = new TwImageInfo { Width = 2, Height = 2, X = new TwFix { Whole = 2400 }, Y = new TwFix { Whole = 2400 }, BitsPerPixel = 24, Bits = new short[8] };
                    Page transferred = Twain.SaveDibBytes(dib, info, folder);
                    Assert(Path.GetExtension(transferred.Path) == ".tif", "Native acquisition saves TIFF");
                    using (Bitmap image = transferred.Load()) { Assert(image.GetPixel(0, 0).R > 240 && image.GetPixel(1, 1).B > 240, "DIB color/orientation"); }
                    Assert(Math.Abs(transferred.DpiX - 2400) < 1, "DIB transfer DPI");
                    log.AppendLine("PASS: native DIB film-frame conversion preserves pixels, orientation and DPI.");
                    const int stripWidth = 3000, stripHeight = 23000, stripStride = stripWidth * 3;
                    IntPtr stripHandle = GlobalAlloc(0x42, (UIntPtr)(40 + stripStride * stripHeight));
                    Assert(stripHandle != IntPtr.Zero, "Whole-strip test allocation");
                    Page native;
                    try
                    {
                        IntPtr pixels = GlobalLock(stripHandle); Assert(pixels != IntPtr.Zero, "Whole-strip test lock");
                        try
                        {
                            Marshal.WriteInt32(pixels, 0, 40); Marshal.WriteInt32(pixels, 4, stripWidth); Marshal.WriteInt32(pixels, 8, -stripHeight);
                            Marshal.WriteInt16(pixels, 12, 1); Marshal.WriteInt16(pixels, 14, 24);
                            Marshal.WriteByte(pixels, 40 + 2, 255); // Red top-left, top-down DIB.
                            Marshal.WriteByte(pixels, 40 + stripStride * (stripHeight - 1), 255); // Blue bottom-left.
                        }
                        finally { GlobalUnlock(stripHandle); }
                        info.Width = stripWidth; info.Height = stripHeight;
                        native = Twain.SaveDib(stripHandle, info, folder);
                    }
                    finally { GlobalFree(stripHandle); }
                    Page strip = Twain.CompleteDib(native);
                    using (var image = (Bitmap)Image.FromFile(strip.Path))
                    {
                        Assert(image.Width == stripWidth && image.Height == stripHeight, "Whole-strip dimensions");
                        Assert(image.GetPixel(0, 0).R == 255 && image.GetPixel(0, stripHeight - 1).B == 255, "Whole-strip pixel preservation/orientation");
                    }
                    using (Bitmap image = strip.LoadPreview(1600)) Assert(image.Width == 209 && image.Height == 1600, "Whole-strip bounded preview");
                    Assert(Math.Abs(strip.DpiX - 2400) < 1 && !File.Exists(native.Path), "Whole-strip DPI and successful native temporary cleanup");
                    log.AppendLine("PASS: 3000 x 23000 whole-strip native buffer, lossless conversion and bounded preview (207 MB pixels). Peak working set: " + (System.Diagnostics.Process.GetCurrentProcess().PeakWorkingSet64 / 1048576) + " MiB.");
                    using (var form = new DeskForm())
                    {
                        form.ShowInTaskbar = false; form.Opacity = 0; form.Show(); Application.DoEvents(); form.PerformLayout();
                        form.RefreshScanners();
                        string status = form.StatusText;
                        Assert(status.Contains("Ready - Canon"), "Canon source selected in the film UI");
                        using (var screenshot = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(screenshot, new Rectangle(0, 0, form.Width, form.Height)); Export.Tiff(screenshot, Path.Combine(folder, "app-preview.tif")); }
                        form.Close();
                        log.AppendLine("PASS: film app constructed and rendered. " + status);
                    }
                }
                else throw new ArgumentException("Supported diagnostics: --self-test or --probe");
                File.WriteAllText(report, log.ToString()); return 0;
            }
            catch (Exception ex) { log.AppendLine("FAIL: " + ex); File.WriteAllText(report, log.ToString()); return 1; }
        }
        private static void TestLarge48Bit(string folder, StringBuilder log)
        {
            const int width = 5872, height = 30000, batchRows = 128, stride = width * 6;
            string path = Path.Combine(folder, "large-48bit.tif");
            byte[] chunk = new byte[stride * batchRows];
            using (var writer = new FilmRows(path, FilmInfo(width, height)))
                for (int y = 0; y < height; y += batchRows)
                {
                    int count = Math.Min(batchRows, height - y);
                    for (int n = 0; n < count; n++)
                    {
                        ushort marker = (ushort)(y + n + 23);
                        chunk[n * stride] = (byte)marker; chunk[n * stride + 1] = (byte)(marker >> 8);
                        chunk[n * stride + stride - 2] = (byte)~marker; chunk[n * stride + stride - 1] = (byte)(~marker >> 8);
                    }
                    writer.Append(new TwImageMem { Columns = width, Rows = (uint)count, BytesPerRow = stride, YOffset = (uint)y, BytesWritten = (uint)(count * stride) }, chunk);
                    if (y + count == height) writer.Complete();
                }
            using (Tiff tiff = Tiff48.Open(path, "r"))
            {
                byte[] row = new byte[stride];
                for (int y = 0; y < height; y++)
                {
                    ushort marker = (ushort)(y + 23);
                    Assert(tiff.ReadScanline(row, y) && BitConverter.ToUInt16(row, 0) == marker && BitConverter.ToUInt16(row, stride - 2) == (ushort)~marker, "Large 48-bit row order and low-bit precision");
                }
            }
            using (Bitmap image = Page.Read(path).LoadPreview(1600))
                Assert(image.Height == 1600 && image.Width == 313, "Large 48-bit bounded preview");
            long peak = System.Diagnostics.Process.GetCurrentProcess().PeakWorkingSet64;
            Assert(peak < 256 * 1048576L, "48-bit streaming must not allocate the entire 1 GB image");
            log.AppendLine("PASS: 5872 x 30000 48-bit streamed transfer and sequential decode (1,056,960,000 bytes of pixels), row markers, bounded preview. Peak working set: " + peak / 1048576 + " MiB.");
        }
        private static TwImageInfo FilmInfo(int width, int height, int dpi = FilmPreset.Dpi)
        {
            return new TwImageInfo { Width = width, Height = height, X = new TwFix { Whole = (short)dpi }, Y = new TwFix { Whole = (short)dpi }, BitsPerPixel = 48, Samples = 3, PixelType = 2, Bits = new short[] { 16, 16, 16, 0, 0, 0, 0, 0 } };
        }
        private static byte[] FilmRow(int width, int y)
        {
            var bytes = new byte[width * 6];
            for (int x = 0; x < width; x++)
                for (int channel = 0; channel < 3; channel++)
                {
                    ushort value = (ushort)((x * 1207 + y * 1777 + channel * 11939 + 23) & 65535);
                    bytes[x * 6 + channel * 2] = (byte)value; bytes[x * 6 + channel * 2 + 1] = (byte)(value >> 8);
                }
            return bytes;
        }
        private static void VerifySamples(string path, int width, int height)
        {
            using (Tiff tiff = Tiff48.Open(path, "r"))
            {
                Assert(Tiff48.Int(tiff, TiffTag.BITSPERSAMPLE) == 16 && Tiff48.Int(tiff, TiffTag.SAMPLESPERPIXEL) == 3, "48-bit TIFF tags");
                var row = new byte[tiff.ScanlineSize()];
                for (int y = 0; y < height; y++) Assert(tiff.ReadScanline(row, y) && row.SequenceEqual(FilmRow(width, y)), "Exact 16-bit samples, row " + y);
            }
        }
        private static void Test48Bit(string folder, StringBuilder log, int dpi = FilmPreset.Dpi)
        {
            const int width = 37, height = 19, stride = width * 6 + 8;
            TwImageInfo info = FilmInfo(width, height, dpi);
            string prefix = dpi == 4800 ? "film48" : "film96";
            string path = Path.Combine(folder, prefix + "-fixture.tif");
            Export.Atomic(path, delegate(string temp)
            {
                using (var writer = new FilmRows(temp, info, dpi))
                {
                    for (int y = 0; y < height; y += 7)
                    {
                        int count = Math.Min(7, height - y); var bytes = new byte[stride * count];
                        for (int n = 0; n < count; n++) Buffer.BlockCopy(FilmRow(width, y + n), 0, bytes, n * stride, width * 6);
                        writer.Append(new TwImageMem { BytesPerRow = stride, Columns = width, Rows = (uint)count, YOffset = (uint)y, BytesWritten = (uint)bytes.Length }, bytes);
                    }
                    writer.Complete();
                }
            });
            VerifySamples(path, width, height);
            Page film = Page.Read(path);
            Assert(film.BitsPerPixel == 48 && film.Width == width && film.Height == height && film.DpiX == dpi && film.DpiY == dpi, "48-bit dimensions/depth/DPI");
            using (Bitmap preview = film.LoadPreview(1600))
            {
                byte[] first = FilmRow(width, 0);
                Assert(preview.Width == width && preview.Height == height && preview.GetPixel(0, 0).G == (BitConverter.ToUInt16(first, 2) + 128) / 257, "48-bit preview channel order");
            }
            for (int n = 0; n < 4; n++)
            {
                film.Rotate(); VerifySamples(film.Path, width, height);
                using (Bitmap preview = film.LoadPreview(16)) Assert(Math.Max(preview.Width, preview.Height) == 16, "48-bit bounded rotated preview");
                Assert(film.BitsPerPixel == 48 && film.Width == (n % 2 == 0 ? height : width), "48-bit rotation dimensions");
            }
            Assert(File.Exists(path), "48-bit rotation preserves original");
            string copy = Path.Combine(folder, prefix + "-copy.tif"); Export.Image(film, copy);
            Assert(File.ReadAllBytes(copy).SequenceEqual(File.ReadAllBytes(film.Path)), "48-bit TIFF copy preserves entire file");
            try { Export.Image(film, Path.Combine(folder, prefix + "-lossy.jpg")); throw new Exception("48-bit JPEG silently accepted"); } catch (InvalidOperationException) { }
            TwImageInfo wrong = info; wrong.BitsPerPixel = 24;
            try { FilmPreset.Validate(wrong, dpi); throw new Exception("24-bit preset accepted"); } catch (InvalidOperationException) { }
            wrong = info; wrong.X = new TwFix { Whole = (short)(dpi == 4800 ? 9600 : 4800) };
            try { FilmPreset.Validate(wrong, dpi); throw new Exception("Incorrect X DPI accepted"); } catch (InvalidOperationException) { }
            wrong.Y = wrong.X;
            string mismatch = Path.Combine(folder, prefix + "-mismatched.tif");
            try { using (var rows = new FilmRows(mismatch, wrong, dpi)) { } throw new Exception("Mismatched preset saved a file"); } catch (InvalidOperationException) { }
            Assert(!File.Exists(mismatch), "Resolution mismatch is rejected before opening a TIFF");
            wrong = info; wrong.Y = new TwFix { Whole = 19200 };
            try { FilmPreset.Validate(wrong, dpi); throw new Exception("Incorrect Y DPI accepted"); } catch (InvalidOperationException) { }
            try { FilmPreset.Validate(info, 19200); throw new Exception("Unsupported preset accepted"); } catch (ArgumentOutOfRangeException) { }
            string failed = Path.Combine(folder, prefix + "-incomplete.tif");
            try
            {
                Export.Atomic(failed, delegate(string temp) { using (var rows = new FilmRows(temp, info, dpi)) rows.Complete(); });
                throw new Exception("Incomplete 48-bit transfer accepted");
            }
            catch (IOException) { }
            Assert(!File.Exists(failed), "Incomplete transfer does not publish TIFF");
            using (var rows = new FilmRows(Path.Combine(folder, prefix + "-invalid-fixture.tif"), info, dpi))
            {
                try { rows.Append(new TwImageMem { Columns = width, Rows = 1, YOffset = 1, BytesPerRow = width * 6, BytesWritten = width * 6 }, FilmRow(width, 0)); throw new Exception("Out-of-order transfer accepted"); } catch (InvalidOperationException) { }
                try { rows.Append(new TwImageMem { Columns = width, Rows = 1, BytesPerRow = width * 6, BytesWritten = 1 }, FilmRow(width, 0)); throw new Exception("Truncated transfer accepted"); } catch (InvalidOperationException) { }
            }
            log.AppendLine("PASS: " + dpi + " dpi preset: exact 16-bit RGB samples survive buffered transfer, padding, TIFF, four rotations, import and copy; preview helper is bounded. Incorrect depth/DPI, truncated/out-of-order/incomplete transfers and lossy saving are rejected.");
        }
    }
}
