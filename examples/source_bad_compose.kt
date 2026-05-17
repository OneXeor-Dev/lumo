/**
 * Anchor file for `lumo-source check --file …`.
 *
 * Three deliberate violations the AST checker should find:
 *   1. `Modifier.size(32.dp)` on an IconButton — below Material 48dp tap
 *      target (a11y / high).
 *   2. `Color(0xFFAA0000)` hardcoded brand red — bypasses theme tokens
 *      (token / medium).
 *   3. `RoundedCornerShape(13.dp)` — not on the default radius scale
 *      (consistency / low).
 *
 * Counter-cases (must NOT trip): MaterialTheme references. They are
 * exactly the pattern Lumo wants to encourage.
 */

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun BadScreen() {
    Column(modifier = Modifier.padding(16.dp)) {  // 16 is on scale — fine
        IconButton(onClick = {}, modifier = Modifier.size(32.dp)) { }  // ← undersized_tap_target

        Surface(color = Color(0xFFAA0000)) { }   // ← hardcoded_color
        Surface(color = MaterialTheme.colorScheme.primary) { }  // counter — fine

        Surface(shape = RoundedCornerShape(13.dp)) { }  // ← off_scale_radius
        Surface(shape = RoundedCornerShape(12.dp)) { }  // counter — fine
    }
}
