using System;

namespace ScanDesk
{
    internal static class FilmPreset
    {
        public const int Dpi = 4800;
        public static void CheckResolution(int dpi)
        {
            if (dpi != 4800 && dpi != 9600) throw new ArgumentOutOfRangeException("dpi", "Choose the 4800 or 9600 dpi film preset.");
        }
        public static string Name(int dpi) { CheckResolution(dpi); return "FilmDesk " + dpi + " - orange negative"; }
        public static string Summary(int dpi)
        {
            CheckResolution(dpi);
            return "Film / Color Positive Film\n" + dpi + " dpi / 48-bit color / 100%\nLossless TIFF / corrections off\n" +
                (dpi == 9600 ? "Exceeds horizontal optical resolution" : "Within optical resolution on both axes");
        }
        public static string Instructions(int dpi)
        {
            CheckResolution(dpi);
            return
            "In Canon ScanGear > Advanced Mode:\r\n\r\n" +
            "Source: Color Positive Film (preserves the orange negative)\r\n" +
            "Scan Area: 35mm Strip; Whole Film Image view\r\n" +
            "Color Mode: Color(48bit)\r\n" +
            "Output Resolution: " + dpi + " dpi\r\n" +
            "Output Size: Flexible; scale 100%\r\n\r\n" +
            "Check Output Resolution in Canon's screen: it can keep\r\n" +
            "the previous DPI when opened, even after a TWAIN request.\r\n\r\n" +
            "Preferences > Scan: Enable 48/16 bit Output\r\n" +
            "Preferences > Color Settings: None\r\n" +
            "Preferences > Scanner: Quiet Mode checked\r\n\r\n" +
            "Unsharp Mask / sharpening: OFF\r\n" +
            "Dust and scratches, fading, grain, backlight: None / OFF\r\n" +
            "Auto tone, auto color, Image Adjustment: None / OFF\r\n" +
            "Descreen: OFF (some controls are absent for positive film)\r\n" +
            "High Quality: OFF; no custom tone corrections\r\n\r\n" +
            "After Preview: use Whole Film Image view with manual crops,\r\n" +
            "enable Manual Exposure at 100%, and check scale 100%.\r\n" +
            (dpi == 9600 ?
                "Canon limits scans to 30,000 pixels tall and 1.8 GB.\r\n" +
                "At 9600 dpi, use overlapping manual regions up to\r\n" +
                "2.5 inches tall for the approximately 1.22-inch film\r\n" +
                "window, to stay below both limits. No frame detection.\r\n" +
                "Canon's optical film resolution is 4800 x 9600 dpi;\r\n" +
                "square 9600 dpi exceeds the horizontal optical limit.\r\n" :
                "Canon documents a 30,000-pixel height limit (6.25 inches\r\n" +
                "at 4800 dpi). A longer strip may need two overlapping\r\n" +
                "manual regions, without automatic frame detection.\r\n") +
            "Save these driver settings under Favorite Settings as:\r\n" +
            Name(dpi) + "\r\n\r\n" +
            "Scans save automatically as 48-bit TIFF. FilmDesk checks\r\n" +
            "the received resolution and bit depth. Film type, corrections,\r\n" +
            "scale and Quiet Mode must be checked in Canon's screen.\r\n" +
            "Match the selected preset's DPI; do not enlarge output.\r\n" +
            "Use Negative Film only when you want Canon to invert colors.";
        }

        public static void Validate(TwImageInfo info, int dpi = Dpi)
        {
            CheckResolution(dpi);
            if (float.IsNaN(info.X.Value) || float.IsNaN(info.Y.Value) || Math.Abs(info.X.Value - dpi) > 1 || Math.Abs(info.Y.Value - dpi) > 1)
                throw new InvalidOperationException("This film preset requires " + dpi + " dpi on both axes. Set ScanGear to " + dpi + " dpi, Flexible output and 100% scale.");
            if (info.BitsPerPixel != 48 || info.Samples != 3 || info.PixelType != 2 || info.Planar != 0 || info.Compression != 0 || info.Bits == null || info.Bits.Length < 3 || info.Bits[0] != 16 || info.Bits[1] != 16 || info.Bits[2] != 16)
                throw new InvalidOperationException("This film preset requires uncompressed, interleaved 48-bit RGB. In Preferences > Scan enable 48/16 bit Output, then select Color(48bit). No image was downconverted.");
        }
    }
}
