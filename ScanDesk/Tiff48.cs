using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using BitMiracle.LibTiff.Classic;

namespace ScanDesk
{
    // Keep 16-bit samples outside System.Drawing, which can silently reduce them to 8 bits.
    internal static class Tiff48
    {
        public static Tiff Open(string path, string mode)
        {
            Tiff tiff = Tiff.Open(path, mode);
            if (tiff == null) throw new IOException("Cannot open TIFF: " + path);
            return tiff;
        }
        public static int Int(Tiff tiff, TiffTag tag) { return tiff.GetFieldDefaulted(tag)[0].ToInt(); }
        public static Page Read(string path)
        {
            using (Tiff tiff = Open(path, "r"))
            {
                if (Int(tiff, TiffTag.BITSPERSAMPLE) != 16) return null;
                if (tiff.NumberOfDirectories() != 1 || tiff.IsTiled() || Int(tiff, TiffTag.SAMPLESPERPIXEL) != 3 || Int(tiff, TiffTag.PHOTOMETRIC) != (int)Photometric.RGB || Int(tiff, TiffTag.PLANARCONFIG) != (int)PlanarConfig.CONTIG || Int(tiff, TiffTag.SAMPLEFORMAT) != (int)SampleFormat.UINT)
                    throw new InvalidOperationException("48-bit import requires a single-page, stripped, unsigned RGB TIFF with interleaved samples.");
                int orientation = Int(tiff, TiffTag.ORIENTATION);
                if (orientation != 1 && orientation != 3 && orientation != 6 && orientation != 8)
                    throw new InvalidOperationException("Unsupported 48-bit TIFF orientation.");
                int width = Int(tiff, TiffTag.IMAGEWIDTH), height = Int(tiff, TiffTag.IMAGELENGTH);
                float x = tiff.GetField(TiffTag.XRESOLUTION) == null ? 96 : tiff.GetField(TiffTag.XRESOLUTION)[0].ToFloat();
                float y = tiff.GetField(TiffTag.YRESOLUTION) == null ? 96 : tiff.GetField(TiffTag.YRESOLUTION)[0].ToFloat();
                if (Int(tiff, TiffTag.RESOLUTIONUNIT) == (int)ResUnit.CENTIMETER) { x *= 2.54f; y *= 2.54f; }
                bool swapped = orientation == 6 || orientation == 8;
                return new Page { Path = path, Width = swapped ? height : width, Height = swapped ? width : height, DpiX = swapped ? y : x, DpiY = swapped ? x : y, BitsPerPixel = 48 };
            }
        }
        public static Tiff Create(string path, int width, int height, float x, float y)
        {
            if (width <= 0 || height <= 0 || (long)width * height * 6 > 3500000000L || x <= 0 || y <= 0)
                throw new InvalidOperationException("Invalid or too large 48-bit film image for classic TIFF.");
            Tiff tiff = Open(path, "w");
            try
            {
                if (!tiff.SetField(TiffTag.IMAGEWIDTH, width) || !tiff.SetField(TiffTag.IMAGELENGTH, height) ||
                    !tiff.SetField(TiffTag.SAMPLESPERPIXEL, 3) || !tiff.SetField(TiffTag.BITSPERSAMPLE, 16) ||
                    !tiff.SetField(TiffTag.SAMPLEFORMAT, SampleFormat.UINT) || !tiff.SetField(TiffTag.PHOTOMETRIC, Photometric.RGB) ||
                    !tiff.SetField(TiffTag.PLANARCONFIG, PlanarConfig.CONTIG) || !tiff.SetField(TiffTag.ORIENTATION, Orientation.TOPLEFT) ||
                    !tiff.SetField(TiffTag.COMPRESSION, Compression.LZW) || !tiff.SetField(TiffTag.ROWSPERSTRIP, Math.Max(1, 65536 / checked(width * 6))) ||
                    !tiff.SetField(TiffTag.XRESOLUTION, x) || !tiff.SetField(TiffTag.YRESOLUTION, y) || !tiff.SetField(TiffTag.RESOLUTIONUNIT, ResUnit.INCH))
                    throw new IOException("Cannot set 48-bit TIFF metadata.");
                return tiff;
            }
            catch { tiff.Dispose(); throw; }
        }
        public static Bitmap Preview(Page page, int longestSide)
        {
            using (Tiff tiff = Open(page.Path, "r"))
            {
                int width = Int(tiff, TiffTag.IMAGEWIDTH), height = Int(tiff, TiffTag.IMAGELENGTH);
                double scale = Math.Min(1.0, (double)longestSide / Math.Max(width, height));
                int pw = Math.Max(1, (int)Math.Round(width * scale)), ph = Math.Max(1, (int)Math.Round(height * scale));
                var bitmap = new Bitmap(pw, ph, PixelFormat.Format24bppRgb);
                try
                {
                    var row = new byte[tiff.ScanlineSize()];
                    var display = new byte[((pw * 3 + 3) / 4) * 4];
                    BitmapData pixels = bitmap.LockBits(new Rectangle(0, 0, pw, ph), ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
                    try
                    {
                        int decodedRow = -1;
                        for (int py = 0; py < ph; py++)
                        {
                            int sy = Math.Min(height - 1, (int)((long)py * height / ph));
                            // Compressed strips require sequential reads even when the display skips rows.
                            while (decodedRow < sy)
                                if (!tiff.ReadScanline(row, ++decodedRow)) throw new IOException("Cannot decode 48-bit TIFF preview row.");
                            for (int px = 0; px < pw; px++)
                            {
                                int sx = Math.Min(width - 1, (int)((long)px * width / pw)) * 6;
                                display[px * 3] = (byte)((BitConverter.ToUInt16(row, sx + 4) + 128) / 257);
                                display[px * 3 + 1] = (byte)((BitConverter.ToUInt16(row, sx + 2) + 128) / 257);
                                display[px * 3 + 2] = (byte)((BitConverter.ToUInt16(row, sx) + 128) / 257);
                            }
                            Marshal.Copy(display, 0, IntPtr.Add(pixels.Scan0, py * pixels.Stride), display.Length);
                        }
                    }
                    finally { bitmap.UnlockBits(pixels); }
                    int orientation = Int(tiff, TiffTag.ORIENTATION);
                    if (orientation == 6) bitmap.RotateFlip(RotateFlipType.Rotate90FlipNone);
                    else if (orientation == 3) bitmap.RotateFlip(RotateFlipType.Rotate180FlipNone);
                    else if (orientation == 8) bitmap.RotateFlip(RotateFlipType.Rotate270FlipNone);
                    return bitmap;
                }
                catch { bitmap.Dispose(); throw; }
            }
        }
        public static void Rotate(Page page, string destination)
        {
            Export.Atomic(destination, delegate(string temp)
            {
                File.Copy(page.Path, temp);
                using (Tiff tiff = Open(temp, "r+"))
                {
                    int previous = Int(tiff, TiffTag.ORIENTATION);
                    int next = previous == 1 ? 6 : previous == 6 ? 3 : previous == 3 ? 8 : 1;
                    if (!tiff.SetField(TiffTag.ORIENTATION, next) || !tiff.RewriteDirectory())
                        throw new IOException("Cannot save TIFF orientation.");
                }
            });
        }
    }

    internal sealed class FilmRows : IDisposable
    {
        private readonly Tiff tiff;
        private readonly int width, height;
        public int RowsWritten { get; private set; }
        public FilmRows(string path, TwImageInfo info, int dpi = FilmPreset.Dpi)
        {
            FilmPreset.Validate(info, dpi); width = info.Width; height = info.Height;
            tiff = Tiff48.Create(path, width, height, info.X.Value, info.Y.Value);
        }
        public void Append(TwImageMem transfer, byte[] bytes)
        {
            long rowBytes = (long)width * 6;
            long needed = transfer.Rows == 0 ? 0 : (long)(transfer.Rows - 1) * transfer.BytesPerRow + rowBytes;
            if (transfer.Compression != 0 || transfer.Columns != width || transfer.XOffset != 0 || transfer.YOffset != RowsWritten ||
                transfer.BytesPerRow < rowBytes || transfer.Rows == 0 || (long)RowsWritten + transfer.Rows > height ||
                needed > transfer.BytesWritten || transfer.BytesWritten > bytes.Length)
                throw new InvalidOperationException("Invalid, truncated or out-of-order 48-bit film transfer. No final TIFF was saved.");
            for (int n = 0; n < transfer.Rows; n++)
            {
                if (!tiff.WriteScanline(bytes, checked(n * (int)transfer.BytesPerRow), RowsWritten, 0))
                    throw new IOException("Cannot save 48-bit film samples.");
                RowsWritten++;
            }
        }
        public void Complete()
        {
            if (RowsWritten != height) throw new IOException("The driver returned an incomplete film image.");
            if (!tiff.WriteDirectory()) throw new IOException("Cannot finish the 48-bit TIFF.");
        }
        public void Dispose() { tiff.Dispose(); }
    }
}
