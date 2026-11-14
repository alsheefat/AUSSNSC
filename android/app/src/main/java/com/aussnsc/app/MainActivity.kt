@file:OptIn(ExperimentalMaterial3Api::class)

package com.aussnsc.app

import android.app.Activity
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.core.view.WindowCompat
import androidx.navigation.navArgument
import coil.Coil
import coil.ImageLoader
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Session.init(applicationContext)
        Api.init(applicationContext)
        // pictures use the same HTTPS settings as the API (needed on Android 7)
        Coil.setImageLoader(ImageLoader.Builder(applicationContext).okHttpClient(Api.httpClient).crossfade(true).build())
        setContent { AUSSNSCApp() }
    }
}

@Composable
fun AUSSNSCApp() {
    val nav = rememberNavController()
    val dark = when (Session.theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val scheme = if (dark) darkColorScheme(
        primary = Color(0xFF8AB4F8), onPrimary = Color(0xFF0B1B2B),
        primaryContainer = Color(0xFF1F3A5F), onPrimaryContainer = Color(0xFFD7E6FA),
        secondaryContainer = Color(0xFF24405F), onSecondaryContainer = Color(0xFFDCE8F7),
        background = Color(0xFF101820), onBackground = Color(0xFFE6EDF5),
        surface = Color(0xFF182431), onSurface = Color(0xFFE6EDF5),
        surfaceVariant = Color(0xFF223244), onSurfaceVariant = Color(0xFFB7C4D2),
        outline = Color(0xFF6F8196),
        surfaceContainer = Color(0xFF182431), surfaceContainerHigh = Color(0xFF1E2C3C),
        surfaceContainerHighest = Color(0xFF223244), surfaceContainerLow = Color(0xFF141F2B),
        surfaceContainerLowest = Color(0xFF0D141C),
    ) else lightColorScheme(
        primary = Blue, onPrimary = Color.White,
        primaryContainer = Color(0xFFD7E6FA), onPrimaryContainer = Navy,
        secondaryContainer = Color(0xFFDCE8F7), onSecondaryContainer = Navy,
        background = Canvas, onBackground = Color(0xFF0F1B2A),
        surface = Color.White, onSurface = Color(0xFF0F1B2A),
        surfaceVariant = Color(0xFFE6ECF3), onSurfaceVariant = Color(0xFF53606E),
        outline = Color(0xFF8793A1),
        surfaceContainer = Color.White, surfaceContainerHigh = Color(0xFFF1F5FA),
        surfaceContainerHighest = Color(0xFFE9EEF5), surfaceContainerLow = Color(0xFFF7F9FC),
        surfaceContainerLowest = Color.White,
    )

    // status-bar icons: dark on light screens, light on dark screens and on the blue welcome page
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    val view = LocalView.current
    SideEffect {
        val window = (view.context as? Activity)?.window
        if (window != null) {
            val controller = WindowCompat.getInsetsController(window, view)
            controller.isAppearanceLightStatusBars = !dark && route != "welcome"
            controller.isAppearanceLightNavigationBars = !dark
        }
    }

    // refresh the stored profile once on start (role may have changed since last login)
    LaunchedEffect(Unit) {
        if (Session.loggedIn) {
            try {
                Api.me()
            } catch (e: Exception) {
            }
        }
    }

    MaterialTheme(colorScheme = scheme) {
        NavHost(navController = nav, startDestination = if (Session.loggedIn) "home" else "welcome") {
            composable("welcome") { WelcomeScreen(nav) }
            composable("login") { AuthScreen(nav, register = false) }
            composable("register") { AuthScreen(nav, register = true) }
            composable("home") { HomeScreen(nav) }
            composable("profile") { ProfileScreen(nav) }
            composable("settings") { SettingsScreen(nav) }
            composable("results") { ResultScreen(nav) }
            composable("attendance_mark") { MarkAttendanceScreen(nav) }
            composable(
                "list/{key}?arg={arg}",
                arguments = listOf(
                    navArgument("key") { type = NavType.StringType },
                    navArgument("arg") { type = NavType.StringType; defaultValue = "" },
                ),
            ) { entry ->
                ListPage(nav, entry.arguments?.getString("key") ?: "", entry.arguments?.getString("arg") ?: "")
            }
            composable(
                "form/{key}?arg={arg}",
                arguments = listOf(
                    navArgument("key") { type = NavType.StringType },
                    navArgument("arg") { type = NavType.StringType; defaultValue = "" },
                ),
            ) { entry ->
                FormScreen(nav, entry.arguments?.getString("key") ?: "", entry.arguments?.getString("arg") ?: "")
            }
            composable("chat/{id}", arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
                ChatScreen(nav, entry.arguments?.getInt("id") ?: 0)
            }
            composable("album/{id}", arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
                AlbumScreen(nav, entry.arguments?.getInt("id") ?: 0)
            }
            composable("child/{sid}", arguments = listOf(navArgument("sid") { type = NavType.StringType })) { entry ->
                val sid = entry.arguments?.getString("sid") ?: ""
                MenuPage(
                    nav, "My Child", "Parent",
                    listOf(
                        Tile("Attendance", "Attendance record", "list/attendance?arg=$sid", Icons.Default.Check),
                        Tile("Results", "Published results", "list/results_my?arg=$sid", Icons.Default.Star),
                        Tile("Assignments", "Homework for their class", "list/assignments?arg=$sid", Icons.Default.Edit),
                    ),
                )
            }
        }
    }
}

// ───────────── welcome ─────────────

@Composable
fun WelcomeScreen(nav: NavHostController) {
    Column(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF1960B4), Color(0xFF0B326B))))
            .statusBarsPadding().navigationBarsPadding().padding(24.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column {
            Box(Modifier.size(66.dp).background(Color.White, RoundedCornerShape(20.dp)), contentAlignment = Alignment.Center) {
                Text("A", color = Blue, fontSize = 34.sp, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.height(28.dp))
            Text("AUSSNSC", color = Color.White, fontSize = 34.sp, fontWeight = FontWeight.Bold)
            Text("Ahammad Uddin Shah Shishu Niketan School & College", color = Color.White.copy(alpha = .85f), fontSize = 15.sp)
        }
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("A smarter way to stay connected with your school.", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.SemiBold)
            Button(
                onClick = { nav.navigate("home") { popUpTo(nav.graph.id) { inclusive = true } } },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Blue),
            ) { Text("Explore as Guest") }
            OutlinedButton(
                onClick = { nav.navigate("login") }, modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
            ) { Text("Sign in") }
            TextButton(onClick = { nav.navigate("register") }, modifier = Modifier.fillMaxWidth()) {
                Text("Create an account", color = Color.White)
            }
        }
    }
}

// ───────────── home ─────────────

data class Tile(val title: String, val subtitle: String, val route: String, val icon: ImageVector = Icons.Default.ArrowForward)

private fun exploreTiles(role: String): List<Tile> = listOf(
    Tile("Notices", "Official announcements", "list/notices", Icons.Default.Campaign),
    Tile("Result Search", "Find a published result", "results", Icons.Default.Search),
    Tile("Academic Calendar", "Dates and events", "list/calendar", Icons.Default.DateRange),
    if (role == "student") Tile("Class Routine", "Your weekly timetable", "list/routine?arg=me", Icons.Default.DateRange)
    else Tile("Class Routine", "Pick a class", "list/routine_classes", Icons.Default.DateRange),
    if (role == "student") Tile("Exam Routine", "Your upcoming exams", "list/exam_routine?arg=me", Icons.Default.Edit)
    else Tile("Exam Routine", "Upcoming exams", "list/exam_routine", Icons.Default.Edit),
    Tile("Gallery", "School photos", "list/gallery", Icons.Default.Favorite),
    Tile("Admission", "Information and application", "list/admission", Icons.Default.School),
    Tile("Teacher Directory", "Find teaching staff", "list/teachers", Icons.Default.Person),
    Tile("About School", "School information", "list/about", Icons.Default.Info),
)

private fun roleTiles(role: String): List<Tile> = when (role) {
    "student" -> listOf(
        Tile("My Attendance", "Present, absent, late", "list/attendance", Icons.Default.Check),
        Tile("My Results", "Published results", "list/results_my", Icons.Default.Star),
        Tile("Assignments", "Homework and submissions", "list/assignments", Icons.Default.Edit),
        Tile("Study Materials", "Notes and resources", "list/materials", Icons.Default.Info),
        Tile("Community", "Class channels", "list/channels", Icons.Default.Groups),
    )
    "parent" -> listOf(
        Tile("My Children", "Attendance, results, homework", "list/children", Icons.Default.Person),
        Tile("Link a Child", "Send a verification request", "list/my_links", Icons.Default.Add),
        Tile("Study Materials", "Resources for the class", "list/materials", Icons.Default.Info),
        Tile("Community", "Class channels (read only)", "list/channels", Icons.Default.Groups),
    )
    "teacher" -> listOf(
        Tile("My Classes", "Assigned classes and rosters", "list/my_classes", Icons.Default.School),
        Tile("Mark Attendance", "Record today's attendance", "attendance_mark", Icons.Default.Check),
        Tile("Create Assignment", "Set homework", "form/create_assignment", Icons.Default.Add),
        Tile("Assignments & Reviews", "See submissions", "list/assignments", Icons.Default.Edit),
        Tile("Study Materials", "Shared resources", "list/materials", Icons.Default.Info),
        Tile("Community", "Class channels", "list/channels", Icons.Default.Groups),
        Tile("Moderation", "Reported messages", "list/moderation", Icons.Default.Lock),
    )
    "admin" -> listOf(
        Tile("Dashboard", "School overview", "list/admin_stats", Icons.Default.Home),
        Tile("Pending Parent Links", "Approve or reject", "list/admin_links", Icons.Default.Check),
        Tile("Users", "Roles and accounts", "list/admin_users", Icons.Default.Person),
        Tile("Admission Applications", "Review applicants", "list/admin_apps", Icons.Default.School),
        Tile("Post a Notice", "Publish an announcement", "form/notice", Icons.Default.Campaign),
        Tile("Community", "Channels", "list/channels", Icons.Default.Groups),
        Tile("Moderation", "Reported messages", "list/moderation", Icons.Default.Lock),
    )
    else -> emptyList()
}

@Composable
fun MenuCard(title: String, subtitle: String, icon: ImageVector = Icons.Default.ArrowForward, onClick: () -> Unit) {
    Card(
        Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(42.dp).background(MaterialTheme.colorScheme.primary.copy(alpha = .12f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
            Icon(Icons.Default.ChevronRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun MenuPage(nav: NavHostController, title: String, section: String, tiles: List<Tile>) {
    Scaffold(topBar = { Header(title, section) { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        LazyColumn(Modifier.fillMaxSize().padding(p).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(tiles) { t -> MenuCard(t.title, t.subtitle, t.icon, onClick = { nav.navigate(t.route) }) }
        }
    }
}

@Composable
fun HomeScreen(nav: NavHostController) {
    val role = Session.role
    val name = Session.user?.str("full_name") ?: ""
    Scaffold(
        topBar = {
            Row(
                Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).statusBarsPadding().padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("AUSSNSC", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Navy, modifier = Modifier.weight(1f))
                IconButton(onClick = { nav.navigate("settings") }) { Icon(Icons.Default.Settings, "Settings") }
            }
        },
        bottomBar = {
            NavigationBar {
                listOf("Home" to Icons.Default.Home, "Community" to Icons.Default.Groups, "Academics" to Icons.Default.School, "Notices" to Icons.Default.Campaign, "Profile" to Icons.Default.Person).forEach { (label, icon) ->
                    NavigationBarItem(
                        selected = label == "Home",
                        onClick = {
                            when (label) {
                                "Community" -> nav.navigate("list/channels")
                                "Academics" -> nav.navigate(
                                    when (role) {
                                        "student" -> "list/attendance"
                                        "parent" -> "list/children"
                                        "teacher" -> "list/my_classes"
                                        "admin" -> "list/admin_stats"
                                        else -> "results"
                                    },
                                )
                                "Notices" -> nav.navigate("list/notices")
                                "Profile" -> nav.navigate("profile")
                            }
                        },
                        icon = { Icon(icon, label) }, label = { Text(label) },
                    )
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column {
                    Spacer(Modifier.height(8.dp))
                    Text(if (name.isBlank()) "Welcome!" else "Hello, $name", fontSize = 25.sp, fontWeight = FontWeight.Bold)
                    Text(
                        if (role == "guest") "You're browsing as a guest." else "Signed in as " + cap(role),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF123B70)),
                    shape = RoundedCornerShape(26.dp),
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),
                ) {
                    Box(Modifier.fillMaxWidth().background(Color(0xFF123B70)).padding(20.dp)) {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("AUSSNSC  /  DIGITAL CAMPUS", color = Color(0xFFB9D9F7), fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
                            Text("Your school,\nconnected.", color = Color.White, fontSize = 27.sp, lineHeight = 31.sp, fontWeight = FontWeight.Bold)
                            Text("Learning · Updates · Community", color = Color.White.copy(alpha = .82f), fontSize = 13.sp)
                            Spacer(Modifier.height(2.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf("Academics", "Notices", "Community").forEach { label ->
                                    Surface(color = Color.White.copy(alpha = .13f), shape = RoundedCornerShape(50)) {
                                        Text(label, color = Color.White, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                                    }
                                }
                            }
                        }
                    }
                }
            }
            if (role == "guest") {
                item { LoginPrompt(nav) }
            }
            if (role == "public") {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF4E0)), modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Your account is waiting for verification", fontWeight = FontWeight.Bold, color = Color(0xFF7A4B00))
                            Text(
                                "You can use all public features now. Student, parent and teacher tools unlock after the school verifies you. Parents can send a child-link request below.",
                                fontSize = 13.sp, color = Color(0xFF7A4B00),
                            )
                            TextButton(onClick = { nav.navigate("form/child_link") }) { Text("I'm a parent - link my child") }
                        }
                    }
                }
            }
            val mine = roleTiles(role)
            if (mine.isNotEmpty()) {
                item { Text("Your tools", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp)) }
                items(mine) { t -> MenuCard(t.title, t.subtitle, t.icon, onClick = { nav.navigate(t.route) }) }
            }
            item { Text("Explore", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp)) }
            items(exploreTiles(role)) { t -> MenuCard(t.title, t.subtitle, t.icon, onClick = { nav.navigate(t.route) }) }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

// ───────────── profile ─────────────

@Composable
fun ProfileScreen(nav: NavHostController) {
    var student by remember { mutableStateOf<JSONObject?>(null) }
    LaunchedEffect(Session.access) {
        if (Session.loggedIn) {
            try {
                Api.me()
                if (Session.role == "student") student = Api.obj("GET", "/me/student")
            } catch (e: Exception) {
            }
        }
    }
    val u = Session.user
    Scaffold(topBar = { Header("My Profile", "Account") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        Column(Modifier.fillMaxSize().padding(p).padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (!Session.loggedIn || u == null) {
                Text("You're browsing as a guest.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                LoginPrompt(nav)
                OutlinedButton(onClick = { nav.navigate("register") }, modifier = Modifier.fillMaxWidth()) { Text("Create an account") }
            } else {
                Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(u.str("full_name"), fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text("Role: " + cap(u.str("role", "public")))
                        if (u.str("phone").isNotBlank()) Text("Phone: " + u.str("phone") + if (u.optBoolean("phone_verified")) " (verified)" else " (not verified)")
                        if (u.str("email").isNotBlank()) Text("Email: " + u.str("email") + if (u.optBoolean("email_verified")) " (verified)" else " (not verified)")
                        val s = student
                        if (s != null) Text("Class: " + s.str("class_label") + " · Roll " + s.optInt("roll"))
                    }
                }
                if (u.str("role") == "public") {
                    Text("Student, parent and teacher access is unlocked by the school office after verification.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (u.str("role") == "public" || u.str("role") == "parent") {
                    OutlinedButton(onClick = { nav.navigate("list/my_links") }, modifier = Modifier.fillMaxWidth()) { Text("Child link requests") }
                }
                Button(onClick = { nav.navigate("settings") }, modifier = Modifier.fillMaxWidth()) { Text("Settings") }
                OutlinedButton(
                    onClick = {
                        Session.clear()
                        nav.navigate("welcome") { popUpTo(nav.graph.id) { inclusive = true } }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Sign out") }
            }
        }
    }
}

// ───────────── settings ─────────────

@Composable
fun SettingsScreen(nav: NavHostController) {
    val scope = rememberCoroutineScope()
    val context = androidx.compose.ui.platform.LocalContext.current
    val language = Session.user?.str("language", "en") ?: "en"

    fun save(field: String, value: String) {
        if (!Session.loggedIn) return
        scope.launch {
            try {
                Session.updateUser(Api.obj("PATCH", "/me", JSONObject().put(field, value)))
            } catch (e: Exception) {
                toast(context, "Saved on this phone only (couldn't reach the server).")
            }
        }
    }

    Scaffold(topBar = { Header("Settings", "Account") { nav.popBackStack() } }, containerColor = MaterialTheme.colorScheme.background) { p ->
        Column(Modifier.fillMaxSize().padding(p).padding(18.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Appearance", fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("light" to "Light", "dark" to "Dark", "system" to "System").forEach { (v, label) ->
                    FilterChip(selected = Session.theme == v, onClick = { Session.applyTheme(v); save("theme", v) }, label = { Text(label) })
                }
            }
            Text("Language", fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = language == "en", onClick = { save("language", "en") }, label = { Text("English") })
                FilterChip(selected = language == "bn", onClick = { save("language", "bn") }, label = { Text("বাংলা") })
            }
            Text(
                if (Session.loggedIn) "Your language choice is saved to your account. Full Bangla translation of the app screens is coming."
                else "Sign in to save your language choice. Full Bangla translation of the app screens is coming.",
                fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (Session.loggedIn) {
                OutlinedButton(onClick = { nav.navigate("form/password") }, modifier = Modifier.fillMaxWidth()) { Text("Change password") }
                OutlinedButton(
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        scope.launch {
                            try {
                                Api.request("POST", "/auth/logout-all")
                            } catch (e: Exception) {
                            }
                            Session.clear()
                            nav.navigate("welcome") { popUpTo(nav.graph.id) { inclusive = true } }
                        }
                    },
                ) { Text("Sign out of all devices") }
            }
            Text("AUSSNSC " + "v" + BuildConfig.VERSION_NAME, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
