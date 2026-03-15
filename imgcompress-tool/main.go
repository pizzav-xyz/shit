package main

import (
	"bytes"
	"fmt"
	"image"
	"image/jpeg"
	_ "image/png"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: imgcompress <input_image> [target_size_mb]")
		fmt.Println("Target size is optional (default 8 MB)")
		return
	}

	inputPath := os.Args[1]
	targetSize := 8
	if len(os.Args) >= 3 {
		if val, err := strconv.Atoi(os.Args[2]); err == nil {
			targetSize = val
		}
	}

	err := compressImage(inputPath, targetSize)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
}

func compressImage(inputPath string, targetSizeMB int) error {
	file, err := os.Open(inputPath)
	if err != nil {
		return fmt.Errorf("failed to open input file: %w", err)
	}
	defer file.Close()

	img, format, err := image.Decode(file)
	if err != nil {
		return fmt.Errorf("failed to decode image: %w", err)
	}

	originalInfo, err := os.Stat(inputPath)
	if err != nil {
		return fmt.Errorf("failed to get original file info: %w", err)
	}
	originalSize := originalInfo.Size()
	targetBytes := int64(targetSizeMB) * 1024 * 1024

	fmt.Printf("Original file: %s (%d bytes, %.2f MB)\n", inputPath, originalSize, float64(originalSize)/(1024*1024))
	fmt.Printf("Image format: %s\n", format)
	fmt.Printf("Target size: %d MB (%d bytes)\n", targetSizeMB, targetBytes)

	ext := strings.ToLower(filepath.Ext(inputPath))

	if originalSize < targetBytes && (ext == ".jpg" || ext == ".jpeg" || ext == ".png") {
		fmt.Printf("Image is already under %d MB, copying as is...\n", targetSizeMB)
		return copyFile(inputPath, strings.TrimSuffix(inputPath, filepath.Ext(inputPath))+"_compressed"+filepath.Ext(inputPath))
	}

	var outputBuffer bytes.Buffer
	var bestQuality int

	if format == "jpeg" || format == "jpg" {
		bestQuality, err = findOptimalJPEGQuality(img, int(targetBytes))
		if err != nil {
			return fmt.Errorf("failed to find optimal JPEG quality: %w", err)
		}

		opts := &jpeg.Options{Quality: bestQuality}
		err = jpeg.Encode(&outputBuffer, img, opts)
		if err != nil {
			return fmt.Errorf("failed to encode JPEG: %w", err)
		}
	} else {
		bestQuality, err = findOptimalJPEGQualityForPNG(img, int(targetBytes))
		if err != nil {
			return fmt.Errorf("failed to find optimal JPEG quality for PNG: %w", err)
		}

		opts := &jpeg.Options{Quality: bestQuality}
		err = jpeg.Encode(&outputBuffer, img, opts)
		if err != nil {
			return fmt.Errorf("failed to encode JPEG from PNG: %w", err)
		}
	}

	if int64(outputBuffer.Len()) > targetBytes {
		fmt.Printf("Binary search couldn't achieve target, falling back to quality 10\n")

		var fallbackBuffer bytes.Buffer
		minOpts := &jpeg.Options{Quality: 10}
		err = jpeg.Encode(&fallbackBuffer, img, minOpts)
		if err != nil {
			return fmt.Errorf("failed to encode JPEG with minimum quality: %w", err)
		}

		if int64(fallbackBuffer.Len()) > targetBytes {
			fmt.Printf("Quality 10 still exceeds target, progressively reducing quality\n")

			for quality := 10; quality >= 1; quality-- {
				var progressiveBuffer bytes.Buffer
				progOpts := &jpeg.Options{Quality: quality}
				err = jpeg.Encode(&progressiveBuffer, img, progOpts)
				if err != nil {
					continue
				}

				if int64(progressiveBuffer.Len()) <= targetBytes {
					outputBuffer = progressiveBuffer
					bestQuality = quality
					fmt.Printf("Success with quality %d\n", quality)
					break
				}

				if quality == 1 {
					return fmt.Errorf("even quality 1 produces an image too large. Final size: %d bytes (%.2f MB)",
						progressiveBuffer.Len(), float64(progressiveBuffer.Len())/(1024*1024))
				}
			}
		} else {
			outputBuffer = fallbackBuffer
			bestQuality = 10
		}
	}

	if int64(outputBuffer.Len()) > targetBytes {
		return fmt.Errorf("could not compress image to under %d MB. Final size: %d bytes (%.2f MB)",
			targetSizeMB, outputBuffer.Len(), float64(outputBuffer.Len())/(1024*1024))
	}

	var outputPath string
	if format == "jpeg" || format == "jpg" {
		outputPath = strings.TrimSuffix(inputPath, filepath.Ext(inputPath)) + "_compressed" + filepath.Ext(inputPath)
	} else {
		outputPath = strings.TrimSuffix(inputPath, filepath.Ext(inputPath)) + "_compressed.jpg"
	}

	outputFile, err := os.Create(outputPath)
	if err != nil {
		return fmt.Errorf("failed to create output file: %w", err)
	}
	defer outputFile.Close()

	_, err = outputFile.Write(outputBuffer.Bytes())
	if err != nil {
		return fmt.Errorf("failed to write output file: %w", err)
	}

	fmt.Printf("Successfully compressed image to %s (%d bytes, %.2f MB)\n", outputPath, outputBuffer.Len(), float64(outputBuffer.Len())/(1024*1024))
	fmt.Printf("Achieved %.2f%% of target size, with %d bytes of headroom\n",
		(float64(outputBuffer.Len())/float64(targetBytes))*100,
		targetBytes-int64(outputBuffer.Len()))

	return nil
}

func findOptimalJPEGQuality(img image.Image, targetSize int) (int, error) {
	low := 1
	high := 100
	bestQuality := 1
	bestSize := 0

	for low <= high {
		mid := (low + high) / 2
		var buf bytes.Buffer
		opts := &jpeg.Options{Quality: mid}
		err := jpeg.Encode(&buf, img, opts)
		if err != nil {
			return 0, err
		}

		size := buf.Len()
		if size <= targetSize {
			bestQuality = mid
			bestSize = size
			low = mid + 1
		} else {
			high = mid - 1
		}
	}

	if bestQuality == 1 {
		var buf bytes.Buffer
		opts := &jpeg.Options{Quality: 1}
		err := jpeg.Encode(&buf, img, opts)
		if err != nil {
			return 0, err
		}

		size := buf.Len()
		if size <= targetSize {
			bestQuality = 1
			bestSize = size
		}
	}

	fmt.Printf("Optimal JPEG quality found: %d (size: %d bytes)\n", bestQuality, bestSize)
	return bestQuality, nil
}

func findOptimalJPEGQualityForPNG(img image.Image, targetSize int) (int, error) {
	low := 1
	high := 100
	bestQuality := 1
	bestSize := 0

	for low <= high {
		mid := (low + high) / 2
		var buf bytes.Buffer
		opts := &jpeg.Options{Quality: mid}
		err := jpeg.Encode(&buf, img, opts)
		if err != nil {
			return 0, err
		}

		size := buf.Len()
		if size <= targetSize {
			bestQuality = mid
			bestSize = size
			low = mid + 1
		} else {
			high = mid - 1
		}
	}

	if bestQuality == 1 {
		var buf bytes.Buffer
		opts := &jpeg.Options{Quality: 1}
		err := jpeg.Encode(&buf, img, opts)
		if err != nil {
			return 0, err
		}

		size := buf.Len()
		if size <= targetSize {
			bestQuality = 1
			bestSize = size
		}
	}

	fmt.Printf("Optimal JPEG quality for PNG conversion: %d (size: %d bytes)\n", bestQuality, bestSize)
	return bestQuality, nil
}

func copyFile(src, dst string) error {
	srcFile, err := os.Open(src)
	if err != nil {
		return err
	}
	defer srcFile.Close()

	dstFile, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	buf := make([]byte, 1024*1024)
	for {
		n, err := srcFile.Read(buf)
		if err != nil && err != io.EOF {
			return err
		}
		if n == 0 {
			break
		}

		if _, err := dstFile.Write(buf[:n]); err != nil {
			return err
		}
	}

	return nil
}
