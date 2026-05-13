param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$PreviewPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$code = @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class HairOmbreRecolor
{
    private static byte ClampByte(double value)
    {
        if (value < 0) return 0;
        if (value > 255) return 255;
        return (byte)Math.Round(value);
    }

    public static void Process(string sourcePath, string outputPath, string previewPath)
    {
        using (var src = new Bitmap(sourcePath))
        using (var outBmp = new Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb))
        using (var previewBmp = new Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb))
        {
            Rectangle rect = new Rectangle(0, 0, src.Width, src.Height);
            BitmapData srcData = src.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            BitmapData outData = outBmp.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
            BitmapData previewData = previewBmp.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);

            try
            {
                int stride = srcData.Stride;
                int bytes = Math.Abs(stride) * src.Height;
                byte[] srcBytes = new byte[bytes];
                byte[] outBytes = new byte[bytes];
                byte[] previewBytes = new byte[bytes];

                Marshal.Copy(srcData.Scan0, srcBytes, 0, bytes);

                const double previewBg = 112.0; // neutral mid-gray
                const double rootValue = 242.0; // near-white
                const double tipValue = 18.0;   // near-black, not absolute zero

                for (int y = 0; y < src.Height; y++)
                {
                    double topness = 1.0 - ((double)y / Math.Max(1, src.Height - 1));
                    double gradient = tipValue + ((rootValue - tipValue) * topness);

                    for (int x = 0; x < src.Width; x++)
                    {
                        int idx = (y * stride) + (x * 4);
                        byte b = srcBytes[idx + 0];
                        byte g = srcBytes[idx + 1];
                        byte r = srcBytes[idx + 2];
                        byte a = srcBytes[idx + 3];

                        double lum = (0.2126 * r) + (0.7152 * g) + (0.0722 * b);
                        double maxc = Math.Max(r, Math.Max(g, b));
                        double minc = Math.Min(r, Math.Min(g, b));
                        double chroma = maxc - minc;

                        // Source atlas is mostly black background with colored strands/cards.
                        // Treat bright or colorful pixels as visible hair.
                        double mask = 0.0;
                        if (maxc > 10 || chroma > 8 || lum > 8)
                        {
                            double brightnessMask = Math.Min(1.0, Math.Max(0.0, (maxc - 6.0) / 48.0));
                            double colorMask = Math.Min(1.0, Math.Max(0.0, chroma / 42.0));
                            double alphaMask = a / 255.0;
                            mask = Math.Max(alphaMask, Math.Max(brightnessMask, colorMask));
                        }

                        double localShade = 0.78 + ((lum / 255.0) * 0.55);
                        double value = gradient * localShade;
                        byte gray = ClampByte(value);

                        // Atlas output: keep only inferred visible pixels, black elsewhere.
                        byte outGray = ClampByte(gray * mask);
                        outBytes[idx + 0] = outGray;
                        outBytes[idx + 1] = outGray;
                        outBytes[idx + 2] = outGray;
                        outBytes[idx + 3] = 255;

                        // Preview output: composite the inferred mask onto gray background.
                        byte previewGray = ClampByte((gray * mask) + (previewBg * (1.0 - mask)));
                        previewBytes[idx + 0] = previewGray;
                        previewBytes[idx + 1] = previewGray;
                        previewBytes[idx + 2] = previewGray;
                        previewBytes[idx + 3] = 255;
                    }
                }

                Marshal.Copy(outBytes, 0, outData.Scan0, bytes);
                Marshal.Copy(previewBytes, 0, previewData.Scan0, bytes);
            }
            finally
            {
                src.UnlockBits(srcData);
                outBmp.UnlockBits(outData);
                previewBmp.UnlockBits(previewData);
            }

            outBmp.Save(outputPath, ImageFormat.Png);
            previewBmp.Save(previewPath, ImageFormat.Png);
        }
    }
}
"@

Add-Type -TypeDefinition $code -ReferencedAssemblies System.Drawing

$sourceFull = (Resolve-Path -LiteralPath $SourcePath).Path
$outputDir = Split-Path -Parent $OutputPath
$previewDir = Split-Path -Parent $PreviewPath
if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }
if ($previewDir) { New-Item -ItemType Directory -Force -Path $previewDir | Out-Null }

[HairOmbreRecolor]::Process($sourceFull, $OutputPath, $PreviewPath)

Write-Host "SAVED_ATLAS: $OutputPath"
Write-Host "SAVED_PREVIEW: $PreviewPath"
