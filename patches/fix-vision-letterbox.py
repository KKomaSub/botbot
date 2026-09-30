from pathlib import Path

p = Path('project/vision/src/main/kotlin/dev/pylarl/vision/TensorPreprocessor.kt')
p.write_text(r'''package dev.pylarl.vision

import dev.pylarl.capture.CapturedFrame
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min

object TensorPreprocessor {
    private data class Scratch(val width: Int, val height: Int, val buffer: FloatBuffer)
    private val scratch = ThreadLocal<Scratch>()

    fun prepareRgba(frame: CapturedFrame, inputWidth: Int = 640, inputHeight: Int = 640): FloatBuffer {
        require(frame.width > 0 && frame.height > 0 && inputWidth > 0 && inputHeight > 0)
        val scale = min(inputWidth.toFloat() / frame.width, inputHeight.toFloat() / frame.height)
        val resizedWidth = max(1, (frame.width * scale).toInt())
        val resizedHeight = max(1, (frame.height * scale).toInt())
        val plane = inputWidth * inputHeight
        val count = plane * 3

        var local = scratch.get()
        if (local == null || local.width != inputWidth || local.height != inputHeight) {
            local = Scratch(
                inputWidth,
                inputHeight,
                ByteBuffer.allocateDirect(count * 4).order(ByteOrder.nativeOrder()).asFloatBuffer(),
            )
            scratch.set(local)
        }

        val out = local.buffer
        val pad = 128f / 255f
        for (i in 0 until count) out.put(i, pad)

        val src = frame.rgba.duplicate()
        for (y in 0 until resizedHeight) {
            val sy = (y.toLong() * frame.height / resizedHeight).toInt().coerceAtMost(frame.height - 1)
            for (x in 0 until resizedWidth) {
                val sx = (x.toLong() * frame.width / resizedWidth).toInt().coerceAtMost(frame.width - 1)
                val pixel = (sy * frame.width + sx) * 4
                val offset = y * inputWidth + x
                // Desktop Pyla feeds OpenCV BGR frames directly to the model.
                // MediaProjection gives RGBA, so reorder R,G,B -> B,G,R here.
                out.put(offset, (src.get(pixel + 2).toInt() and 0xff) / 255f)
                out.put(plane + offset, (src.get(pixel + 1).toInt() and 0xff) / 255f)
                out.put(2 * plane + offset, (src.get(pixel).toInt() and 0xff) / 255f)
            }
        }
        out.position(0)
        out.limit(count)
        return out
    }
}
''')

p = Path('project/vision/src/main/kotlin/dev/pylarl/vision/model/OrtInferenceSessionFactory.kt')
s = p.read_text()
old = '''                val outShape = (session.outputInfo.values.first().info as TensorInfo).shape
                return YoloPostprocessor.decode(raw.toFloatArray(), outShape, 0.55f, 0.6f, model.classes)
'''
new = '''                val outShape = (session.outputInfo.values.first().info as TensorInfo).shape
                val decoded = YoloPostprocessor.decode(raw.toFloatArray(), outShape, 0.55f, 0.6f, model.classes)
                val scale = minOf(w.toFloat() / frame.width, h.toFloat() / frame.height)
                val resizedWidth = maxOf(1, (frame.width * scale).toInt())
                val resizedHeight = maxOf(1, (frame.height * scale).toInt())
                val scaleX = frame.width.toFloat() / resizedWidth
                val scaleY = frame.height.toFloat() / resizedHeight
                return decoded.map { detection ->
                    detection.copy(
                        left = (detection.left * scaleX).coerceIn(0f, frame.width.toFloat()),
                        top = (detection.top * scaleY).coerceIn(0f, frame.height.toFloat()),
                        right = (detection.right * scaleX).coerceIn(0f, frame.width.toFloat()),
                        bottom = (detection.bottom * scaleY).coerceIn(0f, frame.height.toFloat()),
                    )
                }
'''
if old not in s:
    raise SystemExit('Ort postprocess anchor not found')
p.write_text(s.replace(old, new, 1))

# Keep the unit test aligned with the source model's actual BGR input convention and letterbox behavior.
p = Path('project/vision/src/test/kotlin/dev/pylarl/vision/TensorPreprocessorTest.kt')
p.write_text(r'''package dev.pylarl.vision

import dev.pylarl.capture.CapturedFrame
import java.nio.ByteBuffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class TensorPreprocessorTest {
    @Test fun rgba_is_reordered_to_bgr_chw_for_source_model() {
        val b = ByteBuffer.allocateDirect(16)
        b.put(byteArrayOf(
            255.toByte(),0,0,255.toByte(),
            0,255.toByte(),0,255.toByte(),
            0,0,255.toByte(),255.toByte(),
            255.toByte(),255.toByte(),255.toByte(),255.toByte(),
        )).flip()
        val f = CapturedFrame(2,2,1,b){}
        val out = TensorPreprocessor.prepareRgba(f,2,2)
        val a = FloatArray(12); out.get(a)
        assertArrayEquals(
            floatArrayOf(0f,0f,1f,1f, 0f,1f,0f,1f, 1f,0f,0f,1f),
            a,
            0.0001f,
        )
    }

    @Test fun wide_frame_keeps_aspect_ratio_and_pads_bottom() {
        val b = ByteBuffer.allocateDirect(4 * 4 * 2)
        repeat(8) { b.put(byteArrayOf(255.toByte(),0,0,255.toByte())) }
        b.flip()
        val f = CapturedFrame(4,2,1,b){}
        val out = TensorPreprocessor.prepareRgba(f,4,4)
        val a = FloatArray(4 * 4 * 3); out.get(a)
        val pad = 128f / 255f
        // B plane: source red becomes 0 in the active top half, padding stays gray below.
        assertEquals(0f, a[0], 0.0001f)
        assertEquals(0f, a[7], 0.0001f)
        assertEquals(pad, a[8], 0.0001f)
        assertEquals(pad, a[15], 0.0001f)
    }
}
''')
print('vision letterbox+BGR patch applied')
