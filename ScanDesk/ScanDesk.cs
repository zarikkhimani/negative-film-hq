using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace ScanDesk
{
    internal static class Program
    {
        public static readonly string Root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length > 0) return Tests.Run(args);
            Application.Run(new DeskForm());
            return 0;
        }
    }

    internal sealed class Page
    {
        public string Path;
        public int Width, Height;
        public int BitsPerPixel;
        public float DpiX, DpiY;
        public static Page Read(string path)
        {
            string extension = System.IO.Path.GetExtension(path).ToLowerInvariant();
            if (extension == ".tif" || extension == ".tiff") { Page highDepth = Tiff48.Read(path); if (highDepth != null) return highDepth; }
            using (Image image = Image.FromFile(path))
            {
                if (System.Drawing.Image.GetPixelFormatSize(image.PixelFormat) > 32 || image.PixelFormat == PixelFormat.Format16bppGrayScale)
                    throw new InvalidOperationException("High-depth images must be single-page, stripped 48-bit RGB TIFFs. Other high-depth formats and 16-bit grayscale are unsupported.");
                if (image.GetFrameCount(FrameDimension.Page) > 1)
                    throw new InvalidOperationException("Import individual film-frame files; multipage TIFF import is not supported.");
                return new Page { Path = path, Width = image.Width, Height = image.Height,
                    DpiX = image.HorizontalResolution > 0 ? image.HorizontalResolution : 96,
                    DpiY = image.VerticalResolution > 0 ? image.VerticalResolution : 96, BitsPerPixel = System.Drawing.Image.GetPixelFormatSize(image.PixelFormat) };
            }
        }
        public Bitmap Load()
        {
            if (BitsPerPixel == 48) throw new InvalidOperationException("Use the bounded preview for 48-bit film; full image conversion through System.Drawing would lose precision.");
            using (Image raw = Image.FromFile(Path))
            {
                var copy = new Bitmap(raw);
                copy.SetResolution(DpiX, DpiY);
                return copy;
            }
        }
        public Bitmap LoadPreview(int longestSide)
        {
            if (longestSide < 1) throw new ArgumentOutOfRangeException("longestSide");
            if (BitsPerPixel == 48) return Tiff48.Preview(this, longestSide);
            using (Image raw = Image.FromFile(Path))
            {
                double scale = Math.Min(1.0, (double)longestSide / Math.Max(Width, Height));
                var preview = new Bitmap(Math.Max(1, (int)Math.Round(Width * scale)), Math.Max(1, (int)Math.Round(Height * scale)));
                try
                {
                    using (Graphics graphics = Graphics.FromImage(preview))
                    { graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic; graphics.DrawImage(raw, 0, 0, preview.Width, preview.Height); }
                    return preview;
                }
                catch { preview.Dispose(); throw; }
            }
        }
        public void Rotate()
        {
            string rotated = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(Path), "rotated-" + Guid.NewGuid().ToString("N") + ".tif");
            if (BitsPerPixel == 48) Tiff48.Rotate(this, rotated);
            else using (Bitmap image = Load())
            {
                image.RotateFlip(RotateFlipType.Rotate90FlipNone);
                image.SetResolution(DpiY, DpiX);
                Export.Tiff(image, rotated);
            }
            // Keep the original image on disk for recovery.
            Page updated = Read(rotated);
            Path = updated.Path; Width = updated.Width; Height = updated.Height; DpiX = updated.DpiX; DpiY = updated.DpiY; BitsPerPixel = updated.BitsPerPixel;
        }
        public override string ToString() { return System.IO.Path.GetFileName(Path) + "  (" + Width + " x " + Height + ")"; }
    }

    internal static class Export
    {
        public static void Tiff(Bitmap source, string path)
        {
            using (var parameters = new EncoderParameters(1))
            {
                parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Compression, (long)EncoderValue.CompressionLZW);
                source.Save(path, ImageCodecInfo.GetImageEncoders().First(c => c.MimeType == "image/tiff"), parameters);
            }
        }
        public static byte[] Jpeg(Image source)
        {
            using (var rgb = new Bitmap(source.Width, source.Height, PixelFormat.Format24bppRgb))
            using (Graphics g = Graphics.FromImage(rgb))
            using (var stream = new MemoryStream())
            using (var parameters = new EncoderParameters(1))
            {
                rgb.SetResolution(source.HorizontalResolution, source.VerticalResolution);
                g.Clear(Color.White); g.DrawImage(source, new Rectangle(0, 0, rgb.Width, rgb.Height));
                parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, 95L);
                rgb.Save(stream, ImageCodecInfo.GetImageEncoders().First(c => c.MimeType == "image/jpeg"), parameters);
                return stream.ToArray();
            }
        }
        public static void Atomic(string destination, Action<string> write)
        {
            string temp = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                write(temp);
                if (File.Exists(destination)) File.Replace(temp, destination, null);
                else File.Move(temp, destination);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        public static void Image(Page page, string destination)
        {
            string extension = Path.GetExtension(destination).ToLowerInvariant();
            if (extension != ".jpg" && extension != ".jpeg" && extension != ".tif" && extension != ".tiff")
                throw new InvalidOperationException("Choose JPEG or TIFF.");
            if (page.BitsPerPixel == 48)
            {
                if (extension == ".jpg" || extension == ".jpeg") throw new InvalidOperationException("48-bit film must remain TIFF to preserve all samples.");
                Atomic(destination, delegate(string temp) { File.Copy(page.Path, temp); }); return;
            }
            Atomic(destination, delegate(string temp)
            {
                using (var bitmap = (Bitmap)System.Drawing.Image.FromFile(page.Path))
                {
                    bitmap.SetResolution(page.DpiX, page.DpiY);
                    if (extension == ".jpg" || extension == ".jpeg") File.WriteAllBytes(temp, Jpeg(bitmap));
                    else Tiff(bitmap, temp);
                }
            });
        }
    }
}
