package com.nexvary.voice

import android.Manifest
import android.content.Context
import android.net.Uri
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import android.content.pm.ApplicationInfo
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.runtime.CompositionLocalProvider
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val Ink = Color(0xFF090F1D)
private val Panel = Color(0xFF111E34)
private val Edge = Color(0xFF324761)
private val Silver = Color(0xFFE3EAF5)
private val Muted = Color(0xFF9AAFC9)
private val Gold = Color(0xFFF2CB86)
private val Blue = Color(0xFF4EACFF)
private val Aqua = Color(0xFF48E1C5)
private val Warning = Color(0xFFFFD282)

private val voiceTheme = darkColorScheme(
    primary = Gold, onPrimary = Ink,
    secondary = Aqua, onSecondary = Ink,
    background = Ink, onBackground = Silver,
    surface = Panel, onSurface = Silver,
    surfaceVariant = Color(0xFF1B2B44),
    onSurfaceVariant = Muted,
    outline = Edge,
    error = Color(0xFFFF8A89)
)

@Composable
fun VoiceApp(audio: VoiceAudioController, onListen: (String) -> Unit) {
    val baseContext = LocalContext.current
    val languagePrefs = remember { baseContext.getSharedPreferences("interface_language",Context.MODE_PRIVATE) }
    var uiLanguage by rememberSaveable { mutableStateOf(languagePrefs.getString("language","ar")?.takeIf { it in setOf("ar","en","fr","de","ru") } ?: "ar") }
    val context = remember(uiLanguage) {
        val config=android.content.res.Configuration(baseContext.resources.configuration)
        val locale=java.util.Locale.forLanguageTag(uiLanguage)
        config.setLocale(locale);config.setLayoutDirection(locale)
        baseContext.createConfigurationContext(config)
    }
    val paired = remember { ComputerPairing.restore(context) }
    val prefs = remember { context.getSharedPreferences("voice_config", Context.MODE_PRIVATE) }
    val live = remember { LiveStreamController(context.applicationContext) }
    var requestLive by remember { mutableStateOf<(() -> Unit)?>(null) }
    val livePermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) requestLive?.invoke()
        else live.stateMessage("تم رفض إذن الميكروفون.")
        requestLive = null
    }
    DisposableEffect(live) { onDispose { live.release() } }
    val debug = remember { (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0 }
    var page by rememberSaveable { mutableIntStateOf(0) }
    var endpoint by rememberSaveable {
        mutableStateOf(paired?.endpoint ?: prefs.getString("endpoint", if (debug) "http://10.0.2.2:8000" else "") ?: "")
    }
    var token by remember { mutableStateOf(paired?.token ?: "") } // Paired token is encrypted in Android Keystore storage.
    var from by rememberSaveable { mutableStateOf("hi") }
    var to by rememberSaveable { mutableStateOf("ar") }
    var conversationInput by rememberSaveable { mutableStateOf("") }
    var previewInput by rememberSaveable { mutableStateOf("") }
    var conversationResult by remember { mutableStateOf<VoiceResult?>(null) }
    var previewResult by remember { mutableStateOf<VoiceResult?>(null) }
    var busy by remember { mutableStateOf(false) }
    var subtitleBusy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("ابدأ باختبار الخادم من الإعدادات.") }
    var connected by remember { mutableStateOf<Boolean?>(null) }
    var sourceSrt by remember { mutableStateOf("") }
    var outputSrt by remember { mutableStateOf("") }
    var srtLabel by remember { mutableStateOf("لم يتم اختيار ملف SRT") }
    var videoUri by remember { mutableStateOf<Uri?>(null) }
    var videoName by remember { mutableStateOf("لم يتم اختيار فيديو MP4") }
    var videoJobId by remember { mutableStateOf("") }
    var videoState by remember { mutableStateOf("") }
    var videoBusy by remember { mutableStateOf(false) }
    var videoComplete by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val pair = Direction(from, to)
    val scanComputer = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { raw ->
            scope.launch {
                busy=true;status="جارٍ التحقق من شهادة الكمبيوتر والاقتران…"
                try {
                    val session=withContext(Dispatchers.IO) { ComputerPairing.pair(context,PairingPayload.parse(raw)) }
                    endpoint=session.endpoint;token=session.token
                    prefs.edit().putString("endpoint",endpoint).apply()
                    connected=withContext(Dispatchers.IO) { TranslationClient.health(endpoint,token) }
                    status="تم الاقتران الآمن. يمكنك استخدام الترجمة والصوت والدبلجة عبر الكمبيوتر."
                } catch (_:Exception) {
                    connected=false;status="تعذر الاقتران. اعرض QR جديدًا، وتأكد من نفس Wi-Fi وعدم منع الاتصال بواسطة Firewall. لا تعطل الحماية."
                } finally { busy=false }
            }
        }
    }

    fun doTranslate(input: String, preview: Boolean) {
        if (busy) return
        if (input.isBlank()) { status = "اكتب النص أو سجّله أولًا."; return }
        if (!pair.isValid()) { status = "اختر لغتين مختلفتين."; return }
        busy = true
        status = "جارٍ إرسال الجملة إلى محرك الترجمة…"
        scope.launch {
            try {
                val answer = withContext(Dispatchers.IO) {
                    TranslationClient.translate(endpoint, token, input, pair)
                }
                if (preview) previewResult = answer else conversationResult = answer
                status = "اكتملت ترجمة الجملة. ستسمع الصوت إذا كانت حزمة النطق متاحة."
                audio.speak(answer.translatedText, answer.target)
            } catch (e: Exception) {
                status = "تعذر إتمام الترجمة: " + (e.message ?: "خطأ غير معروف")
            } finally { busy = false }
        }
    }

    LaunchedEffect(audio.captureId) {
        if (audio.captureId > 0) {
            if (page == 2) previewInput = audio.recognized
            else conversationInput = audio.recognized
        }
    }

    val importSrt = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            try {
                val selected = context.contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)
                    ?.use { it.readText() } ?: error("ملف غير قابل للقراءة")
                require(selected.length <= 500_000 && "-->" in selected) { "اختر ملف ترجمة SRT صحيحًا لا يتجاوز 500KB." }
                sourceSrt = selected
                outputSrt = ""
                srtLabel = uri.lastPathSegment?.takeLast(60) ?: "ملف SRT"
                status = "تم استيراد ملف الترجمة؛ يمكنك بدء الترجمة."
            } catch (e: Exception) { status = "تعذر قراءة الملف: " + e.message }
        }
    }
    val saveSrt = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/x-subrip")) { uri ->
        if (uri != null && outputSrt.isNotBlank()) {
            try {
                context.contentResolver.openOutputStream(uri)?.writer(Charsets.UTF_8)?.use { it.write(outputSrt) }
                    ?: error("تعذر فتح الملف للكتابة")
                status = "تم حفظ ملف SRT المترجم."
            } catch (e: Exception) { status = "تعذر حفظ الملف: " + e.message }
        }
    }

    val saveDubSrt = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/x-subrip")) { uri ->
        if(uri!=null && videoJobId.isNotBlank()) scope.launch {
            try {
                withContext(Dispatchers.IO) { VideoClient.download(context,endpoint,token,videoJobId,uri,subtitles=true) }
                videoState="تم حفظ ملف SRT الزمني للدبلجة."
            } catch(_:Exception) { videoState="تعذر حفظ ملف الترجمة؛ تحقق من الاتصال وجاهزية المهمة." }
        }
    }

    val pickMp4 = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            videoUri = uri
            videoName = uri.lastPathSegment?.takeLast(70) ?: "video.mp4"
            videoJobId = ""
            videoComplete=false
            videoState = "تم اختيار الفيديو. اضغط بدء الدبلجة لإرساله إلى خادمك."
        }
    }
    val saveMp4 = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("video/mp4")) { uri ->
        if (uri != null && videoJobId.isNotBlank()) {
            scope.launch {
                videoState = "تنزيل الفيديو المترجم..."
                try {
                    withContext(Dispatchers.IO) {
                        VideoClient.download(context, endpoint, token, videoJobId, uri)
                    }
                    videoState = "تم حفظ ملف MP4 المترجم."
                } catch (e: Exception) {
                    videoState = "فشل حفظ الفيديو: " + (e.message ?: "خطأ")
                }
            }
        }
    }

    CompositionLocalProvider(LocalContext provides context, androidx.compose.ui.platform.LocalLayoutDirection provides if(uiLanguage=="ar") LayoutDirection.Rtl else LayoutDirection.Ltr) {
        MaterialTheme(colorScheme = voiceTheme) {
            Scaffold(
                containerColor = Ink,
                bottomBar = {
                    NavigationBar(containerColor = Color(0xFF111C30), tonalElevation = 0.dp) {
                        val tabs = listOf(
                            Triple("الرئيسية", Icons.Rounded.Home, 0),
                            Triple("المحادثة", Icons.Rounded.Translate, 1),
                            Triple("الاستوديو", Icons.Rounded.Movie, 2),
                            Triple("الإعدادات", Icons.Rounded.Settings, 3)
                        )
                        tabs.forEach { (title, icon, id) ->
                            NavigationBarItem(
                                selected = page == id,
                                onClick = { page = id },
                                icon = { ColorfulIcon(icon, contentDescription = ui(title)) },
                                label = { Text(ui(title), fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = Ink, selectedTextColor = Gold,
                                    indicatorColor = Gold, unselectedIconColor = Muted,
                                    unselectedTextColor = Muted
                                )
                            )
                        }
                    }
                }
            ) { padding ->
                Box(
                    Modifier.fillMaxSize().padding(padding)
                        .background(Brush.verticalGradient(listOf(Ink, Color(0xFF102342), Ink)))
                ) {
                    Column(
                        modifier = Modifier.align(Alignment.TopCenter).widthIn(max = 760.dp).fillMaxWidth()
                            .verticalScroll(rememberScrollState()).padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(15.dp)
                    ) {
                        BrandHeader(connected)
                        when (page) {
                            0 -> HomeScreen(
                                onConversation = { page = 1 },
                                onStudio = { page = 2 },
                                onSettings = { page = 3 }
                            )
                            1 -> {
                                ScreenTitle("مترجم المحادثات", "تبادل أدوار طبيعي • تحدث أو اكتب • استمع للترجمة")
                                LanguagePair(from, to, { from = it }, { to = it }, {
                                    val temporary = from; from = to; to = temporary
                                })
                                GlassCard {
                                    Text(ui("العبارة الأصلية"), color = Gold, fontWeight = FontWeight.SemiBold)
                                    OutlinedTextField(
                                        value = conversationInput, onValueChange = { conversationInput = it },
                                        modifier = Modifier.fillMaxWidth(),
                                        label = { Text(ui("كلام المتحدث")) }, minLines = 3,
                                        colors = inputColors()
                                    )
                                    ActionButton("التحدث بالميكروفون", Icons.Rounded.Mic, false,
                                        audio.listening) {
                                        if (audio.listening) audio.stop()
                                        else onListen(languageTag(from))
                                    }
                                    ActionButton("ترجم وانطق", Icons.Rounded.Translate, true, busy) {
                                        doTranslate(conversationInput, false)
                                    }
                                }
                                GlassCard {
                                    StatusTag("ترجمة صوتية حقيقية متتابعة • تحتاج خادم ASR وTTS", Aqua)
                                    Text(ui("الاستماع المترجم"), fontSize = 18.sp,
                                        fontWeight = FontWeight.Bold, color = Silver)
                                    Text(ui("يعالج الخادم الصوت كل 3.2 ثانية، مع تأخير إضافي للترجمة والنطق. أوقف الميكروفون عند انتهاء الحوار."),
                                        color = Muted, fontSize = 12.sp)
                                    ActionButton(
                                        if (live.active) "إيقاف الاستماع الصوتي" else "بدء الترجمة من الميكروفون",
                                        if (live.active) Icons.Rounded.Stop else Icons.Rounded.RecordVoiceOver,
                                        true, false
                                    ) {
                                        if (live.active) live.stop()
                                        else {
                                            val startStream = {
                                                audio.stop()
                                                live.start(endpoint, token, from, to)
                                            }
                                            if (ContextCompat.checkSelfPermission(
                                                context, Manifest.permission.RECORD_AUDIO
                                            ) == PackageManager.PERMISSION_GRANTED) startStream()
                                            else {
                                                requestLive = startStream
                                                livePermission.launch(Manifest.permission.RECORD_AUDIO)
                                            }
                                        }
                                    }
                                    Text(ui(live.state), color = Aqua, fontSize = 12.sp)
                                    if (live.translated.isNotBlank()) {
                                        Text(ui("قال المتحدث: ") + live.original, fontSize = 12.sp, color = Muted)
                                        Text(live.translated, fontSize = 20.sp, color = Silver)
                                    }
                                }
                                ResultCard(conversationResult, audio) {
                                    conversationInput = ""
                                    val tmp = from; from = to; to = tmp
                                    conversationResult = null
                                }
                            }
                            2 -> {
                                ScreenTitle("Voice Studio", "أدوات ترجمة الصوت والفيديو")
                                LanguagePair(from, to, { from = it }, { to = it }, {
                                    val temporary = from; from = to; to = temporary
                                })
                                GlassCard {
                                    StatusTag("معاينة ترجمة صوتية — ليست بثًا مباشرًا", Warning)
                                    Text(ui("تجربة التعليق الصوتي"), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                    Text(ui("تحدث بالعربية أو بأي لغة محددة، واستمع للصوت المترجم. توجيه الصوت إلى OBS أو تطبيقات البث ليس مفعّلًا بعد."),
                                        color = Muted, fontSize = 13.sp)
                                    OutlinedTextField(
                                        value = previewInput, onValueChange = { previewInput = it },
                                        modifier = Modifier.fillMaxWidth(),
                                        label = { Text(ui("تعليقك الصوتي")) }, minLines = 2, colors = inputColors()
                                    )
                                    ActionButton("تسجيل جملة", Icons.Rounded.Mic, false, audio.listening) {
                                        if (audio.listening) audio.stop() else onListen(languageTag(from))
                                    }
                                    ActionButton("معاينة التعليق المترجم", Icons.Rounded.VolumeUp, true, busy) {
                                        doTranslate(previewInput, true)
                                    }
                                    previewResult?.let {
                                        Text(it.translatedText, color = Silver, fontSize = 18.sp)
                                        TextButton(onClick = { audio.speak(it.translatedText, it.target) }) {
                                            Text(ui("إعادة الاستماع"), color = Aqua)
                                        }
                                    }
                                }
                                GlassCard {
                                    StatusTag("دبلجة MP4 على الكمبيوتر أو الخادم — مهام معالجة", Aqua)
                                    Text(ui("دبلجة فيديو إلى لغة أخرى"), fontSize = 18.sp,
                                        fontWeight = FontWeight.Bold, color = Silver)
                                    Text(ui("استيراد MP4 بحجم لا يتجاوز 80 ميجابايت. يعالج الخادم الكلام وينشئ صوتًا مترجمًا جديدًا، ثم يمكنك تنزيل الفيديو. يلزم تثبيت نماذج Whisper وArgos وPiper على الخادم."),
                                        color = Muted, fontSize = 12.sp)
                                    Text(videoName, color = Aqua, fontSize = 12.sp)
                                    ActionButton("اختيار فيديو MP4", Icons.Rounded.FileOpen, false, false) {
                                        pickMp4.launch(arrayOf("video/mp4"))
                                    }
                                    ActionButton("بدء الدبلجة على الخادم", Icons.Rounded.Movie, true,
                                        videoBusy || videoUri == null) {
                                        val picked = videoUri
                                        if (!videoBusy && picked != null && pair.isValid()) {
                                            videoBusy = true
                                            videoComplete=false
                                            videoState = "رفع الفيديو إلى الخادم..."
                                            scope.launch {
                                                try {
                                                    videoJobId = withContext(Dispatchers.IO) {
                                                        VideoClient.submit(context, endpoint, token, picked, pair)
                                                    }
                                                    videoState = "بدأت معالجة الفيديو..."
                                                    while (true) {
                                                        delay(3000)
                                                        val result = withContext(Dispatchers.IO) {
                                                            VideoClient.status(endpoint, token, videoJobId)
                                                        }
                                                        val state = result.optString("status")
                                                        when (state) {
                                                            "complete" -> {
                                                                videoComplete=true
                                                                videoState = "اكتملت الدبلجة؛ احفظ الفيديو."
                                                                break
                                                            }
                                                            "cancelled" -> {
                                                                videoState="تم إلغاء الدبلجة بأمان."
                                                                break
                                                            }
                                                            "failed" -> {
                                                                videoState = "فشلت الدبلجة: " + result.optString("error")
                                                                break
                                                            }
                                                            else -> videoState = "الحالة: " + state
                                                        }
                                                    }
                                                } catch (e: Exception) {
                                                    videoState = "عطل في الدبلجة: " + (e.message ?: "خطأ")
                                                } finally { videoBusy = false }
                                            }
                                        }
                                    }
                                    if (videoJobId.isNotBlank() && videoComplete) {
                                        ActionButton("حفظ الفيديو المترجم MP4", Icons.Rounded.FileDownload,
                                            false, false) {
                                            saveMp4.launch("NEXVARY-Voice-Dubbed.mp4")
                                        }
                                        ActionButton("حفظ SRT الزمني للدبلجة",Icons.Rounded.Subtitles,false,false) {
                                            saveDubSrt.launch("NEXVARY-Voice-Dubbed.srt")
                                        }
                                    }
                                    if(videoBusy && videoJobId.isNotBlank()) {
                                        ActionButton("إلغاء مهمة الدبلجة",Icons.Rounded.Cancel,false,false) {
                                            scope.launch {
                                                try {
                                                    withContext(Dispatchers.IO) { VideoClient.cancel(endpoint,token,videoJobId) }
                                                    videoState="تم طلب الإلغاء الآمن؛ ننتظر انتهاء المقطع الجاري."
                                                } catch(_:Exception) { videoState="تعذر إرسال طلب الإلغاء؛ تحقق من الاتصال." }
                                            }
                                        }
                                    }
                                    if (videoState.isNotBlank()) Text(ui(videoState), color = Aqua,
                                        fontSize = 12.sp)
                                }
                                GlassCard {
                                    StatusTag("ترجمة ملف SRT مع الحفاظ على التوقيت", Blue)
                                    Text(ui("ترجمة نصوص الفيديو"), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                    Text(ui("استيراد الترجمة الزمنية SRT، ترجمتها مع الحفاظ على التوقيت، ثم حفظها. لتوليد الصوت المترجم استخدم بطاقة دبلجة MP4 أعلاه."),
                                        color = Muted, fontSize = 13.sp)
                                    Text(ui(srtLabel), color = Aqua, fontSize = 12.sp)
                                    ActionButton("اختيار ملف SRT", Icons.Rounded.FileOpen, false, false) {
                                        importSrt.launch(arrayOf("text/*", "application/x-subrip", "*/*"))
                                    }
                                    ActionButton("ترجمة ملف التوقيت", Icons.Rounded.Translate, true,
                                        subtitleBusy || sourceSrt.isEmpty()) {
                                        if (!subtitleBusy && sourceSrt.isNotBlank() && pair.isValid()) {
                                            subtitleBusy = true
                                            status = "تجري ترجمة ملف SRT…"
                                            scope.launch {
                                                try {
                                                    outputSrt = withContext(Dispatchers.IO) {
                                                        TranslationClient.translateSrt(endpoint, token, sourceSrt, pair)
                                                    }
                                                    status = "نجحت الترجمة. احفظ ملف SRT الناتج."
                                                } catch (e: Exception) {
                                                    status = "فشلت ترجمة الملف: " + (e.message ?: "خطأ غير معروف")
                                                } finally { subtitleBusy = false }
                                            }
                                        }
                                    }
                                    if (outputSrt.isNotBlank()) {
                                        ActionButton("حفظ ملف SRT المترجم", Icons.Rounded.FileDownload, false, false) {
                                            saveSrt.launch("NEXVARY-" + from + "-" + to + ".srt")
                                        }
                                    }
                                }
                            }
                            else -> {
                                ScreenTitle("الإعدادات والاتصال", "الخادم الآمن • التحكم في الحساب والصوت")
                                GlassCard {
                                    Text(ui("لغة الواجهة"),fontWeight=FontWeight.Bold,color=Gold)
                                    var languageMenu by remember { mutableStateOf(false) }
                                    val interfaceChoices=listOf("ar" to "العربية","en" to "English","fr" to "Français","de" to "Deutsch","ru" to "Русский")
                                    Box(Modifier.fillMaxWidth()) {
                                        OutlinedButton(onClick={languageMenu=true},modifier=Modifier.fillMaxWidth()) {
                                            Text(interfaceChoices.first { it.first==uiLanguage }.second,color=Gold)
                                        }
                                        DropdownMenu(expanded=languageMenu,onDismissRequest={languageMenu=false}) {
                                            interfaceChoices.forEach { (code,name) ->
                                                DropdownMenuItem(text={Text(name)},onClick={uiLanguage=code;languageMenu=false;languagePrefs.edit().putString("language",code).apply()})
                                            }
                                        }
                                    }
                                    Text(ui("تغيير اللغة لا يغيّر لغتي الترجمة."),color=Muted,fontSize=12.sp)
                                }
                                GlassCard {
                                    Text(ui("ربط الكمبيوتر — دون كتابة عنوان أو مفتاح"), fontWeight = FontWeight.SemiBold, color = Gold)
                                    Text(ui("افتح مركز إعداد الذكاء الاصطناعي على الكمبيوتر، فعّل ربط Android، ثم امسح الرمز. يلزم نفس Wi-Fi. تتم المعالجة على الكمبيوتر."),color=Muted)
                                    ActionButton("مسح QR لربط الكمبيوتر",Icons.Rounded.QrCodeScanner,true,busy) {
                                        scanComputer.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                            .setPrompt(UiStrings.render("امسح رمز NEXVARY الظاهر على الكمبيوتر",context)).setBeepEnabled(false).setOrientationLocked(false))
                                    }
                                    if(ComputerPairing.active!=null) {
                                        Text(ui("الكمبيوتر مقترن؛ مفتاح الاتصال محفوظ مشفرًا. تنتهي الجلسة بعد 8 ساعات أو عند إيقاف الربط."),color=Aqua)
                                        ActionButton("نسيان الكمبيوتر وإيقاف المحادثة",Icons.Rounded.LinkOff,false,busy) {
                                            live.stop();ComputerPairing.forget(context);token="";endpoint="";connected=null
                                            prefs.edit().remove("endpoint").apply();status="تم نسيان الكمبيوتر. أعد مسح QR للربط."
                                        }
                                    } else {
                                    Text(ui("إعداد خادم آخر يدويًا (اختياري)"),fontWeight=FontWeight.SemiBold,color=Gold)
                                    OutlinedTextField(
                                        value = endpoint, onValueChange = {
                                            endpoint = it; connected = null
                                            prefs.edit().putString("endpoint", it).apply()
                                        },
                                        modifier = Modifier.fillMaxWidth(),
                                        label = { Text("HTTPS endpoint") },
                                        singleLine = true, textStyle = TextStyle(textDirection = TextDirection.Ltr),
                                        colors = inputColors()
                                    )
                                    OutlinedTextField(
                                        value = token, onValueChange = { token = it },
                                        modifier = Modifier.fillMaxWidth(),
                                        label = { Text(ui("API Token — لا يتم حفظه")) },
                                        singleLine = true,
                                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                                        textStyle = TextStyle(textDirection = TextDirection.Ltr),
                                        colors = inputColors()
                                    )
                                    }
                                    ActionButton("اختبار اتصال الخادم", Icons.Rounded.Cloud, true, busy) {
                                        scope.launch {
                                            busy = true
                                            try {
                                                connected = withContext(Dispatchers.IO) {
                                                    TranslationClient.health(endpoint, token)
                                                }
                                                status = if (connected == true) "الخادم متصل؛ تحقق من تثبيت نماذج الترجمة." else "الخادم الخفيف يستجيب لكن عامل الترجمة غير متصل أو غير جاهز."
                                            } catch (e: Exception) {
                                                connected = false
                                                status = "فشل الاتصال: " + (e.message ?: "خطأ غير معروف")
                                            } finally { busy = false }
                                        }
                                    }
                                    Text(ui("إذا تغير عنوان الكمبيوتر أو أُغلق الربط، اعرض QR جديدًا. لا تحتاج إلى VPS للربط على الشبكة الخاصة. مفاتيح الخادم اليدوية لا تُحفظ."),
                                        color = Muted, fontSize = 12.sp)
                                }
                                GlassCard {
                                    Text(ui("الصوت والسماعات"), fontWeight = FontWeight.Bold)
                                    Text(ui("تستخدم الجمل المسجلة خدمات الكلام في Android. تستخدم الترجمة الصوتية المتتابعة محرك الكمبيوتر. يخرج الصوت عبر مسار Android بما فيه سماعات Bluetooth المقترنة."),
                                        color = Muted)
                                    Text(ui("النصوص مؤقتة؛ الترجمة الصوتية تعمل بمقاطع 3.2 ثانية إضافة إلى زمن المعالجة. استخدم سماعة رأس لتقليل الصدى."),
                                        color = Muted, fontSize = 12.sp)
                                }
                            }
                        }
                        if (audio.message.isNotBlank() && (page == 1 || page == 2)) {
                            Text(ui(audio.message), color = Aqua, fontSize = 12.sp)
                        }
                        StatusNotice(status)
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }
        }
    }
}

private fun languageTag(code: String): String =
    Languages.choices.firstOrNull { it.code == code }?.tag ?: "en-US"

@Composable
private fun BrandHeader(connected: Boolean?) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Surface(shape = RoundedCornerShape(18.dp), color = Gold) {
            ColorfulIcon(Icons.Rounded.GraphicEq, "NEXVARY", tint = Ink,
                modifier = Modifier.padding(11.dp).size(32.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text("NEXVARY  VOICE", color = Silver, fontSize = 23.sp, fontWeight = FontWeight.Black)
            Text("INTELLIGENT LANGUAGE BRIDGE", color = Muted, fontSize = 10.sp)
        }
        Surface(
            color = Color(0xFF1A2B45),
            shape = RoundedCornerShape(50),
            border = BorderStroke(1.dp, Edge)
        ) {
            Text(
                ui(when (connected) { true -> "● متصل"; false -> "● غير متصل"; null -> "◌ غير مختبر" }),
                color = when (connected) { true -> Aqua; false -> Warning; null -> Muted },
                fontSize = 11.sp,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
            )
        }
    }
}

@Composable
private fun ScreenTitle(title: String, description: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(ui(title), fontSize = 25.sp, fontWeight = FontWeight.Bold, color = Silver)
        Text(ui(description), color = Muted, fontSize = 13.sp)
    }
}

@Composable
private fun GlassCard(content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Panel,
        shape = RoundedCornerShape(24.dp),
        border = BorderStroke(1.dp, Edge),
        tonalElevation = 0.dp
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content
        )
    }
}

@Composable
private fun HomeScreen(onConversation: () -> Unit, onStudio: () -> Unit, onSettings: () -> Unit) {
    Surface(
        color = Color.Transparent, shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth()
            .background(Brush.horizontalGradient(listOf(Color(0xFF173252), Color(0xFF102038))),
                RoundedCornerShape(26.dp)),
        border = BorderStroke(1.dp, Edge)
    ) {
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            StatusTag("VOICE INTELLIGENCE", Aqua)
            Text(ui("تواصل بلا حواجز لغوية"), color = Silver, fontSize = 29.sp,
                fontWeight = FontWeight.Black, lineHeight = 36.sp)
            Text(ui("ترجمة المحادثات ونطقها ودبلجة MP4 وترجمة SRT داخل استوديو واحد."),
                color = Muted, fontSize = 15.sp, lineHeight = 25.sp)
            ActionButton("ابدأ محادثة", Icons.Rounded.ArrowForward, true, false, onConversation)
        }
    }
    FeatureCard("محادثة ثنائية الاتجاه", "تبديل اللغات، ميكروفون، ترجمة نصية ونطق صوتي",
        Icons.Rounded.Translate, Aqua, onConversation)
    FeatureCard("استوديو التعليق والفيديو", "معاينة الصوت ودبلجة MP4 وترجمة SRT",
        Icons.Rounded.Movie, Blue, onStudio)
    FeatureCard("ربط الكمبيوتر", "ضبط عنوان الخادم وفحص الاتصال",
        Icons.Rounded.Cloud, Gold, onSettings)
    GlassCard {
        Text(ui("المعالجة والخصوصية"), color = Gold, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        Text(ui("تعمل الترجمة الصوتية ودبلجة MP4 على الكمبيوتر المقترن. لا يثبّت التطبيق نماذج الذكاء الاصطناعي داخل الهاتف ولا يوجه الصوت إلى تطبيقات أخرى."),
            fontSize = 13.sp, color = Muted)
    }
}

@Composable
private fun FeatureCard(title: String, detail: String, icon: ImageVector, color: Color, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        color = Panel, shape = RoundedCornerShape(21.dp), border = BorderStroke(1.dp, Edge)
    ) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(13.dp)
        ) {
            Surface(color = color.copy(alpha = 0.13f), shape = RoundedCornerShape(15.dp)) {
                ColorfulIcon(icon, title, tint = color, modifier = Modifier.padding(13.dp).size(28.dp))
            }
            Column(Modifier.weight(1f)) {
                Text(ui(title), fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Silver)
                Text(ui(detail), color = Muted, fontSize = 12.sp, lineHeight = 19.sp)
            }
            ColorfulIcon(Icons.Rounded.ChevronLeft, null, tint = color)
        }
    }
}

@Composable
private fun LanguagePair(
    from: String, to: String, setFrom: (String) -> Unit, setTo: (String) -> Unit, swap: () -> Unit
) {
    GlassCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            Box(Modifier.weight(1f)) { LanguageMenu("من", from, setFrom) }
            IconButton(onClick = swap) {
                ColorfulIcon(Icons.Rounded.SwapHoriz, "تبديل اللغتين", tint = Gold, modifier = Modifier.size(27.dp))
            }
            Box(Modifier.weight(1f)) { LanguageMenu("إلى", to, setTo) }
        }
    }
}

@Composable
private fun LanguageMenu(label: String, selected: String, onSelected: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val current = Languages.choices.firstOrNull { it.code == selected }
    Column {
        Text(ui(label), fontSize = 11.sp, color = Muted)
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Silver),
            border = BorderStroke(1.dp, Edge)) {
            Text(current?.title ?: selected, fontSize = 12.sp, maxLines = 1)
            ColorfulIcon(Icons.Rounded.ArrowDropDown, null, tint = Gold, modifier = Modifier.size(18.dp))
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            Languages.choices.forEach { language ->
                DropdownMenuItem(
                    text = { Text(language.title) },
                    onClick = { onSelected(language.code); expanded = false }
                )
            }
        }
    }
}

@Composable
private fun StatusTag(label: String, color: Color) {
    Surface(color = color.copy(alpha = 0.12f), shape = RoundedCornerShape(50),
        border = BorderStroke(1.dp, color.copy(alpha = 0.35f))) {
        Text(ui(label), color = color, fontSize = 11.sp,
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp))
    }
}

@Composable
private fun ActionButton(
    title: String, icon: ImageVector, primary: Boolean, disabled: Boolean, onClick: () -> Unit
) {
    Button(
        onClick = onClick, enabled = !disabled, modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (primary) Gold else Color(0xFF263C5A),
            contentColor = if (primary) Ink else Silver
        ),
        shape = RoundedCornerShape(14.dp)
    ) {
        ColorfulIcon(icon, title, modifier = Modifier.size(21.dp))
        Spacer(Modifier.width(8.dp))
        Text(ui(title), fontWeight = FontWeight.Bold, fontSize = 14.sp)
    }
}

@Composable
private fun ResultCard(result: VoiceResult?, audio: VoiceAudioController, onReply: () -> Unit) {
    GlassCard {
        Text(ui("الترجمة الصوتية"), color = Gold, fontWeight = FontWeight.Bold)
        if (result == null) {
            Text(ui("ستظهر الترجمة هنا فور إتمام الطلب."), color = Muted)
        } else {
            Text(result.translatedText, fontSize = 21.sp, color = Silver,
                fontWeight = FontWeight.Medium, lineHeight = 32.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = { audio.speak(result.translatedText, result.target) }) {
                    ColorfulIcon(Icons.Rounded.VolumeUp, null, tint = Aqua)
                    Text(ui("استمع مجددًا"), color = Aqua, fontSize = 12.sp)
                }
                TextButton(onClick = onReply) {
                    ColorfulIcon(Icons.Rounded.SwapHoriz, null, tint = Gold)
                    Text(ui("رد باللغة الأخرى"), color = Gold, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun StatusNotice(value: String) {
    Surface(color = Color(0xFF16263B), shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Edge)) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            ColorfulIcon(Icons.Rounded.Info, null, tint = Blue, modifier = Modifier.size(19.dp))
            Spacer(Modifier.width(9.dp))
            Text(ui(value), color = Silver, fontSize = 12.sp, lineHeight = 20.sp)
        }
    }
}

@Composable
private fun inputColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = Gold, unfocusedBorderColor = Edge,
    focusedTextColor = Silver, unfocusedTextColor = Silver,
    focusedLabelColor = Gold, unfocusedLabelColor = Muted,
    cursorColor = Gold
)
