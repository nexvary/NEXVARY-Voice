package com.nexvary.voice
import androidx.compose.runtime.Composable
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

/** Bundled filled colour assets, retaining colour in all themes. */
@Composable
internal fun ColorfulIcon(imageVector: ImageVector, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    val resource = when(imageVector.name.substringAfterLast('.')) {
        "ArrowDropDown" -> R.drawable.ic_nv_arrow_drop_down
        "ArrowForward" -> R.drawable.ic_nv_arrow_forward
        "Cancel" -> R.drawable.ic_nv_cancel
        "ChevronLeft" -> R.drawable.ic_nv_chevron_left
        "Cloud" -> R.drawable.ic_nv_cloud
        "FileDownload" -> R.drawable.ic_nv_file_download
        "FileOpen" -> R.drawable.ic_nv_file_open
        "GraphicEq" -> R.drawable.ic_nv_graphic_eq
        "Home" -> R.drawable.ic_nv_home
        "Info" -> R.drawable.ic_nv_info
        "LinkOff" -> R.drawable.ic_nv_link_off
        "Mic" -> R.drawable.ic_nv_mic
        "Movie" -> R.drawable.ic_nv_movie
        "QrCodeScanner" -> R.drawable.ic_nv_qr_code_scanner
        "RecordVoiceOver" -> R.drawable.ic_nv_record_voice_over
        "Settings" -> R.drawable.ic_nv_settings
        "Stop" -> R.drawable.ic_nv_stop
        "Subtitles" -> R.drawable.ic_nv_subtitles
        "SwapHoriz" -> R.drawable.ic_nv_swap_horiz
        "Translate" -> R.drawable.ic_nv_translate
        "VolumeUp" -> R.drawable.ic_nv_volume_up
        else -> R.drawable.ic_nv_info
    }
    Image(painterResource(resource), contentDescription, modifier.size(24.dp))
}
