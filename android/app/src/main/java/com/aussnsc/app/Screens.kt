@file:OptIn(ExperimentalMaterial3Api::class)

package com.aussnsc.app

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

val Blue = Color(0xFF1455A0)
val Navy = Color(0xFF0B326B)
val Canvas = Color(0xFFF3F6FA)

fun toast(context: android.content.Context, message: String?) {
    Toast.makeText(context, message ?: "Something went wrong", Toast.LENGTH_LONG).show()
}

// ───────────── shared pieces ─────────────

@Composable
fun Header(title: String, subtitle: String? = null, onBack: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).statusBarsPadding().padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back") }
        Column {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            if (subtitle != null) Text(subtitle, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun Loading(message: String = "Loading...") {
    Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        CircularProgressIndicator()
        Spacer(Modifier.height(12.dp))
        Text(message, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun ErrorCard(message: String, onRetry: (() -> Unit)?) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(message, color = MaterialTheme.colorScheme.onErrorContainer)
            if (onRetry != null) TextButton(onClick = onRetry) { Text("Try again") }
        }
    }
}

@Composable
fun LoginPrompt(nav: NavHostController) {
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFEAF2FC))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Sign in to continue", fontWeight = FontWeight.Bold, color = Navy)
            Text("This part of the app is for verified students, parents and staff.", color = Navy, fontSize = 13.sp)
            Button(onClick = { nav.navigate("login") }, modifier = Modifier.fillMaxWidth()) { Text("Sign in") }
        }
    }
}

@Composable
fun EntryCard(e: Entry, onClick: (() -> Unit)?) {
    var expanded by remember { mutableStateOf(false) }
    val base = Modifier.fillMaxWidth()
    val mod = if (onClick != null) base.clickable(onClick = onClick)
    else if (e.body.isNotBlank()) base.clickable { expanded = !expanded }
    else base
    Card(mod, shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(e.title, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                if (e.badge.isNotBlank()) Text(e.badge, color = Blue, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            }
            if (e.subtitle.isNotBlank()) Text(e.subtitle, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (e.body.isNotBlank()) {
                Text(
                    e.body, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp),
                    maxLines = if (expanded) Int.MAX_VALUE else 4, overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

// ───────────── generic list page ─────────────

@Composable
fun ListPage(nav: NavHostController, key: String, arg: String) {
    val spec = specs[key]
    if (spec == null) {
        Scaffold(topBar = { Header("Page not found") { nav.popBackStack() } }) { p ->
            Text("This page doesn't exist.", Modifier.padding(p).padding(16.dp))
        }
        return
    }
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    var entries by remember { mutableStateOf<List<Entry>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    var query by remember { mutableStateOf("") }
    var searchTerm by remember { mutableStateOf("") }
    var dialogEntry by remember { mutableStateOf<Entry?>(null) }
    val needLogin = spec.needsLogin && !Session.loggedIn

    LaunchedEffect(key, arg, reload, searchTerm, Session.access) {
        if (needLogin) {
            loading = false
            return@LaunchedEffect
        }
        loading = true
        error = null
        try {
            val path = spec.path(arg, searchTerm)
            entries = spec.map(Api.request("GET", path, null, spec.needsLogin))
        } catch (e: ApiException) {
            error = e.message
            entries = emptyList()
        } catch (e: Exception) {
            error = "Could not load this page."
            entries = emptyList()
        }
        loading = false
    }

    val actionLabel = spec.actionLabel
    val actionRoute = spec.actionRoute
    val err = error

    Scaffold(
        topBar = { Header(spec.title, spec.section) { nav.popBackStack() } },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Text(spec.description, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            if (spec.searchable) {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(query, { query = it }, Modifier.weight(1f), label = { Text("Search") }, singleLine = true)
                        Button(onClick = { searchTerm = query.trim() }) { Text("Go") }
                    }
                }
            }
            if (actionLabel != null && actionRoute != null) {
                item { Button(onClick = { nav.navigate(actionRoute) }, modifier = Modifier.fillMaxWidth()) { Text(actionLabel) } }
            }
            if (needLogin) {
                item { LoginPrompt(nav) }
            } else if (loading) {
                item { Loading("Loading... (the free server may need up to a minute to wake up)") }
            } else if (err != null) {
                item { ErrorCard(err) { reload++ } }
            } else if (entries.isEmpty()) {
                item { Text(spec.empty, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            } else {
                items(entries) { e ->
                    val acts = spec.actions?.invoke(e) ?: emptyList()
                    val click: (() -> Unit)? = when {
                        acts.isNotEmpty() -> ({ dialogEntry = e })
                        e.route != null -> ({ nav.navigate(e.route) })
                        e.url != null -> ({ uriHandler.openUri(e.url) })
                        else -> null
                    }
                    EntryCard(e, click)
                }
            }
        }
    }

    val de = dialogEntry
    if (de != null) {
        val acts = spec.actions?.invoke(de) ?: emptyList()
        AlertDialog(
            onDismissRequest = { dialogEntry = null },
            title = { Text(de.title, maxLines = 2, overflow = TextOverflow.Ellipsis) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (de.body.isNotBlank()) Text(de.body, fontSize = 13.sp)
                    if (de.route != null) TextButton(onClick = { dialogEntry = null; nav.navigate(de.route) }) { Text("Open") }
                    if (de.url != null) TextButton(onClick = { dialogEntry = null; uriHandler.openUri(de.url) }) { Text("Open file / link") }
                    acts.forEach { a ->
                        TextButton(onClick = {
                            dialogEntry = null
                            scope.launch {
                                try {
                                    a.second()
                                } catch (ex: ApiException) {
                                    toast(context, ex.message)
                                } catch (ex: Exception) {
                                    toast(context, "Something went wrong")
                                }
                                reload++
                            }
                        }) { Text(a.first) }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { dialogEntry = null }) { Text("Close") } },
        )
    }
}

// ───────────── generic form page ─────────────

@Composable
fun FieldInput(f: Field, value: String, onChange: (String) -> Unit) {
    when (f.kind) {
        Kind.Choice -> {
            var options by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
            var expanded by remember { mutableStateOf(false) }
            LaunchedEffect(f.key) {
                try {
                    options = f.choices?.invoke() ?: emptyList()
                    if (value.isBlank() && options.isNotEmpty()) onChange(options[0].first)
                } catch (e: Exception) {
                    options = emptyList()
                }
            }
            val shown = options.firstOrNull { it.first == value }?.second ?: ""
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                OutlinedTextField(
                    value = shown, onValueChange = {}, readOnly = true, label = { Text(f.label) },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                )
                ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                    options.forEach { o ->
                        DropdownMenuItem(text = { Text(o.second) }, onClick = { onChange(o.first); expanded = false })
                    }
                }
            }
        }
        else -> OutlinedTextField(
            value = value, onValueChange = onChange, label = { Text(f.label) },
            modifier = Modifier.fillMaxWidth(),
            singleLine = f.kind != Kind.Multiline,
            minLines = if (f.kind == Kind.Multiline) 4 else 1,
            visualTransformation = if (f.kind == Kind.Password) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = when (f.kind) {
                Kind.Number -> KeyboardType.Number
                Kind.Password -> KeyboardType.Password
                else -> KeyboardType.Text
            }),
        )
    }
}

@Composable
fun FormScreen(nav: NavHostController, key: String, arg: String) {
    val spec = forms[key]
    if (spec == null) {
        Scaffold(topBar = { Header("Page not found") { nav.popBackStack() } }) { p -> Text("This form doesn't exist.", Modifier.padding(p).padding(16.dp)) }
        return
    }
    val values = remember { mutableStateMapOf<String, String>() }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var success by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Scaffold(topBar = { Header(spec.title) { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        Column(
            Modifier.fillMaxSize().padding(p).padding(18.dp).verticalScroll(rememberScrollState()).imePadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(spec.intro, color = MaterialTheme.colorScheme.onSurfaceVariant)
            val done = success
            if (spec.needsLogin && !Session.loggedIn) {
                LoginPrompt(nav)
            } else if (done != null) {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFE6F4EA))) {
                    Text(done, Modifier.padding(16.dp), color = Color(0xFF14532D))
                }
                Button(onClick = { nav.popBackStack() }, modifier = Modifier.fillMaxWidth()) { Text("Done") }
            } else {
                spec.fields.forEach { f ->
                    FieldInput(f, values[f.key] ?: "") { values[f.key] = it }
                }
                val err = error
                if (err != null) Text(err, color = MaterialTheme.colorScheme.error)
                Button(
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        val missing = spec.fields.firstOrNull { it.required && (values[it.key] ?: "").isBlank() }
                        if (missing != null) {
                            error = "Please fill in: " + missing.label
                        } else {
                            scope.launch {
                                busy = true
                                error = null
                                try {
                                    val v = spec.fields.associate { it.key to (values[it.key] ?: "").trim() }
                                    success = spec.submit(v, arg)
                                } catch (e: ApiException) {
                                    error = e.message
                                } catch (e: Exception) {
                                    error = "Something went wrong. Please try again."
                                }
                                busy = false
                            }
                        }
                    },
                ) { Text(if (busy) "Please wait..." else spec.submitLabel) }
            }
        }
    }
}

// ───────────── sign in / register ─────────────

@Composable
fun AuthScreen(nav: NavHostController, register: Boolean) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var identifier by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun finish() {
        nav.navigate("home") {
            popUpTo("welcome") { inclusive = true }
            launchSingleTop = true
        }
    }

    fun attempt(block: suspend () -> Unit) {
        scope.launch {
            busy = true
            error = null
            try {
                block()
                finish()
            } catch (e: ApiException) {
                error = e.message
            } catch (e: Exception) {
                error = "Something went wrong. Please try again."
            }
            busy = false
        }
    }

    Scaffold(topBar = { Header(if (register) "Create account" else "Sign in") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        Column(
            Modifier.fillMaxSize().padding(p).padding(18.dp).verticalScroll(rememberScrollState()).imePadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (register) {
                Text("Anyone can create a basic account. Student, parent and teacher access is unlocked after the school verifies you.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text("Full name") }, singleLine = true)
                OutlinedTextField(phone, { phone = it }, Modifier.fillMaxWidth(), label = { Text("Phone number (017xxxxxxxx)") }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
                OutlinedTextField(email, { email = it }, Modifier.fillMaxWidth(), label = { Text("Email (optional if you gave a phone)") }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
            } else {
                OutlinedTextField(identifier, { identifier = it }, Modifier.fillMaxWidth(), label = { Text("Phone number or email") }, singleLine = true)
            }
            OutlinedTextField(
                password, { password = it }, Modifier.fillMaxWidth(),
                label = { Text(if (register) "Create password (8+ characters)" else "Password") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            )
            val err = error
            if (err != null) Text(err, color = MaterialTheme.colorScheme.error)
            Button(
                enabled = !busy, modifier = Modifier.fillMaxWidth(),
                onClick = {
                    if (register) attempt { Api.register(name.trim(), phone.trim(), email.trim(), password) }
                    else attempt { Api.login(identifier.trim(), password) }
                },
            ) { Text(if (busy) "Please wait..." else if (register) "Create account" else "Sign in") }
            OutlinedButton(
                enabled = !busy, modifier = Modifier.fillMaxWidth(),
                onClick = { attempt { Api.googleExchange(GoogleAuth.signIn(context)) } },
            ) { Text("Continue with Google") }
            TextButton(
                onClick = { nav.navigate(if (register) "login" else "register") { launchSingleTop = true } },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (register) "Already have an account? Sign in" else "New here? Create an account") }
            if (busy) Text("Contacting the server... the first request can take up to a minute.", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ───────────── result search (public) ─────────────

@Composable
fun ResultScreen(nav: NavHostController) {
    val scope = rememberCoroutineScope()
    var byRoll by remember { mutableStateOf(true) }
    var value by remember { mutableStateOf("") }
    var className by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var searched by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(topBar = { Header("Result Search", "Academics") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        LazyColumn(Modifier.fillMaxSize().padding(p).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Find a published examination result.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = byRoll, onClick = { byRoll = true }, label = { Text("By roll") })
                        FilterChip(selected = !byRoll, onClick = { byRoll = false }, label = { Text("By name") })
                    }
                    OutlinedTextField(
                        value, { value = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(if (byRoll) "Roll number" else "Student name (3+ letters)") },
                        keyboardOptions = KeyboardOptions(keyboardType = if (byRoll) KeyboardType.Number else KeyboardType.Text),
                    )
                    if (byRoll) OutlinedTextField(className, { className = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Class (e.g. 10) - recommended") })
                    val err = error
                    if (err != null) Text(err, color = MaterialTheme.colorScheme.error)
                    Button(
                        enabled = !busy, modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            val v = value.trim()
                            if (byRoll && v.toIntOrNull() == null) {
                                error = "Enter a valid roll number."
                            } else if (!byRoll && v.length < 3) {
                                error = "Enter at least 3 letters of the name."
                            } else {
                                scope.launch {
                                    busy = true
                                    error = null
                                    try {
                                        val path = if (byRoll) "/results/search?roll=$v" + (if (className.isBlank()) "" else "&class_name=" + enc(className.trim()))
                                        else "/results/search?name=" + enc(v)
                                        results = Api.arr(path, false).objects()
                                        searched = true
                                    } catch (e: ApiException) {
                                        error = e.message
                                    } catch (e: Exception) {
                                        error = "Could not search right now."
                                    }
                                    busy = false
                                }
                            }
                        },
                    ) { Text(if (busy) "Searching..." else "Search result") }
                }
            }
            if (searched && results.isEmpty()) item { Text("No published result matched. Check the details or try again later.") }
            items(results) { r ->
                Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(r.str("student_name"), fontWeight = FontWeight.Bold, fontSize = 17.sp)
                        Text("Class ${r.str("class_name")} ${r.str("section")} · Roll ${r.optInt("roll")}", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("${r.str("exam")} ${r.optInt("exam_year")}", fontWeight = FontWeight.SemiBold)
                        Text("GPA ${r.str("gpa", "-")} · Grade ${r.str("grade", "-")} · ${cap(r.str("status"))}", color = Blue, fontWeight = FontWeight.Bold)
                        r.list("subjects").forEach { s -> Text("${s.str("subject")}: ${s.str("marks", "-")} ${s.str("grade")}", fontSize = 13.sp) }
                    }
                }
            }
        }
    }
}

// ───────────── gallery album ─────────────

@Composable
fun AlbumScreen(nav: NavHostController, id: Int) {
    var album by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(id) {
        try {
            album = Api.obj("GET", "/gallery/albums/$id", null, false)
        } catch (e: ApiException) {
            error = e.message
        } catch (e: Exception) {
            error = "Could not load this album."
        }
    }
    val a = album
    val err = error
    Scaffold(topBar = { Header(a?.str("title") ?: "Album", "Gallery") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        LazyColumn(Modifier.fillMaxSize().padding(p).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (err != null) item { ErrorCard(err, null) }
            else if (a == null) item { Loading() }
            else {
                val photos = a.list("photos")
                if (photos.isEmpty()) item { Text("No photos in this album yet.") }
                items(photos) { ph ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        AsyncImage(
                            model = Api.fileUrl(ph.str("url")), contentDescription = ph.str("caption"),
                            modifier = Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth,
                        )
                        if (ph.str("caption").isNotBlank()) Text(ph.str("caption"), fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

// ───────────── community chat ─────────────

@Composable
fun ChatScreen(nav: NavHostController, id: Int) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var messages by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var channelName by remember { mutableStateOf("Channel") }
    var canPost by remember { mutableStateOf(true) }
    var text by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    val me = Session.user?.optInt("id") ?: -1

    suspend fun fetch() {
        try {
            messages = Api.arr("/channels/$id/messages?limit=60").objects() // newest first
            error = null
        } catch (e: ApiException) {
            error = e.message
        } catch (e: Exception) {
            // transient network error: keep what we have
        }
    }

    LaunchedEffect(id) {
        try {
            val c = Api.arr("/channels").objects().firstOrNull { it.optInt("id") == id }
            if (c != null) {
                channelName = "# " + c.str("name")
                canPost = c.optBoolean("can_post", true)
            }
        } catch (e: Exception) {
        }
        while (true) {
            fetch()
            delay(4000)
        }
    }

    Scaffold(
        topBar = { Header(channelName, "Community") { nav.popBackStack() } },
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            if (canPost) {
                Row(
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).imePadding().padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(text, { text = it }, Modifier.weight(1f), placeholder = { Text("Message this channel...") }, maxLines = 4)
                    IconButton(onClick = {
                        val t = text.trim()
                        if (t.isNotEmpty()) {
                            text = ""
                            scope.launch {
                                try {
                                    Api.request("POST", "/channels/$id/messages", JSONObject().put("body", t))
                                    fetch()
                                } catch (e: ApiException) {
                                    toast(context, e.message)
                                    text = t
                                } catch (e: Exception) {
                                    toast(context, "Could not send")
                                    text = t
                                }
                            }
                        }
                    }) { Icon(Icons.Default.Send, "Send") }
                }
            } else {
                Text(
                    "You can read this channel but not post in it.",
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).navigationBarsPadding().padding(14.dp),
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
    ) { p ->
        val err = error
        LazyColumn(
            Modifier.fillMaxSize().padding(p).padding(horizontal = 14.dp),
            reverseLayout = true, verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (err != null) item { ErrorCard(err, null) }
            items(messages) { m ->
                val mine = m.optInt("user_id", -2) == me
                Card(
                    Modifier.fillMaxWidth().clickable { selected = m }, shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = if (mine) Color(0xFFDCEBFB) else MaterialTheme.colorScheme.surface),
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Text(
                            m.str("author_name") + (if (m.str("author_role") == "teacher" || m.str("author_role") == "admin") " (" + m.str("author_role") + ")" else "") +
                                (if (m.optBoolean("pinned")) "  [pinned]" else ""),
                            fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Blue,
                        )
                        Text(m.str("body"))
                    }
                }
            }
        }
    }

    val sel = selected
    if (sel != null) {
        val staff = Session.role == "teacher" || Session.role == "admin"
        val mid = sel.optInt("id")
        AlertDialog(
            onDismissRequest = { selected = null },
            title = { Text(sel.str("author_name")) },
            text = {
                Column {
                    Text(sel.str("body"))
                    TextButton(onClick = {
                        selected = null
                        scope.launch {
                            try {
                                Api.request("POST", "/messages/$mid/report", JSONObject().put("reason", "Reported from the app"))
                                toast(context, "Reported. A teacher or admin will review it.")
                            } catch (e: ApiException) {
                                toast(context, e.message)
                            }
                        }
                    }) { Text("Report message") }
                    if (isMine(sel, me) || staff) {
                        TextButton(onClick = {
                            selected = null
                            scope.launch {
                                try {
                                    Api.request("DELETE", "/messages/$mid")
                                    fetch()
                                } catch (e: ApiException) {
                                    toast(context, e.message)
                                }
                            }
                        }) { Text("Delete message") }
                    }
                    if (staff) {
                        TextButton(onClick = {
                            selected = null
                            scope.launch {
                                try {
                                    Api.request("POST", "/messages/$mid/pin")
                                    fetch()
                                } catch (e: ApiException) {
                                    toast(context, e.message)
                                }
                            }
                        }) { Text(if (sel.optBoolean("pinned")) "Unpin" else "Pin message") }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { selected = null }) { Text("Close") } },
        )
    }
}

private fun isMine(m: JSONObject, me: Int): Boolean = m.optInt("user_id", -2) == me

// ───────────── teacher: mark attendance ─────────────

@Composable
fun MarkAttendanceScreen(nav: NavHostController) {
    val scope = rememberCoroutineScope()
    var classes by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var classId by remember { mutableStateOf<Int?>(null) }
    var day by remember { mutableStateOf(todayBd()) }
    var roster by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    val status = remember { mutableStateMapOf<Int, String>() }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var info by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Session.access) {
        if (!Session.loggedIn) {
            loading = false
            return@LaunchedEffect
        }
        try {
            classes = Api.arr("/teacher/classes").objects()
            if (classes.size == 1) classId = classes[0].optInt("class_id")
        } catch (e: ApiException) {
            error = e.message
        } catch (e: Exception) {
            error = "Could not load your classes."
        }
        loading = false
    }

    LaunchedEffect(classId, day) {
        val cid = classId ?: return@LaunchedEffect
        info = null
        try {
            roster = Api.arr("/classes/$cid/students").objects()
            val existing = Api.arr("/classes/$cid/attendance?day=$day").objects()
            status.clear()
            roster.forEach { status[it.optInt("id")] = "present" }
            existing.forEach { status[it.optInt("student_id")] = it.str("status") }
            error = null
        } catch (e: ApiException) {
            error = e.message
        } catch (e: Exception) {
            error = "Could not load the roster."
        }
    }

    Scaffold(topBar = { Header("Mark Attendance", "Teacher") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        LazyColumn(Modifier.fillMaxSize().padding(p).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!Session.loggedIn) {
                item { LoginPrompt(nav) }
            } else if (loading) {
                item { Loading() }
            } else {
                val err = error
                if (err != null) item { ErrorCard(err, null) }
                if (classes.isEmpty()) item { Text("No classes are assigned to your account yet. Ask the school admin.") }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        classes.forEach { c ->
                            FilterChip(
                                selected = classId == c.optInt("class_id"), onClick = { classId = c.optInt("class_id") },
                                label = { Text(c.str("class_label").replace("Class ", "").replace(" · Section ", "-")) },
                            )
                        }
                    }
                }
                if (classId != null) {
                    item {
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                                TextButton(onClick = { day = shiftDay(day, -1) }) { Text("< Prev") }
                                Text(day, fontWeight = FontWeight.Bold)
                                TextButton(enabled = day < todayBd(), onClick = { day = shiftDay(day, 1) }) { Text("Next >") }
                            }
                            Text("Tap a student to change: Present -> Absent -> Late.", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    items(roster) { s ->
                        val sid = s.optInt("id")
                        val st = status[sid] ?: "present"
                        Card(
                            Modifier.fillMaxWidth().clickable {
                                status[sid] = when (st) { "present" -> "absent"; "absent" -> "late"; else -> "present" }
                            },
                            shape = RoundedCornerShape(14.dp),
                        ) {
                            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text("${s.optInt("roll")}. ${s.str("full_name")}", Modifier.weight(1f))
                                Text(
                                    cap(st), fontWeight = FontWeight.Bold,
                                    color = when (st) { "present" -> Color(0xFF1B7F3B); "absent" -> Color(0xFFC62828); else -> Color(0xFFB26A00) },
                                )
                            }
                        }
                    }
                    item {
                      Column {
                        val msg = info
                        if (msg != null) Text(msg, color = Color(0xFF1B7F3B))
                        Button(
                            enabled = !busy && roster.isNotEmpty(), modifier = Modifier.fillMaxWidth(),
                            onClick = {
                                scope.launch {
                                    busy = true
                                    error = null
                                    try {
                                        val recs = JSONArray()
                                        roster.forEach { s ->
                                            val sid = s.optInt("id")
                                            recs.put(JSONObject().put("student_id", sid).put("status", status[sid] ?: "present"))
                                        }
                                        val body = JSONObject().put("class_id", classId ?: 0).put("day", day).put("records", recs)
                                        info = Api.obj("POST", "/attendance", body).str("detail", "Saved")
                                    } catch (e: ApiException) {
                                        error = e.message
                                    } catch (e: Exception) {
                                        error = "Could not save attendance."
                                    }
                                    busy = false
                                }
                            },
                        ) { Text(if (busy) "Saving..." else "Save attendance") }
                      }
                    }
                }
            }
        }
    }
}
