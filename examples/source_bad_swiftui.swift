/// Anchor file for `lumo-source check --file …` (SwiftUI side).
///
/// Three deliberate violations the AST checker should find:
///   1. `.frame(width: 32, height: 32)` on a Button — below Apple HIG
///      44pt tap target (a11y / high).
///   2. `Color(red: 0.7, green: 0, blue: 0)` — hardcoded brand colour,
///      bypasses asset-catalog tokens (token / medium).
///   3. `.cornerRadius(13)` — not on the default radius scale
///      (consistency / low).
///
/// Counter-cases (must NOT trip): named constants like `Color.red`,
/// asset-catalog lookups `Color("brandPrimary")`, and token references
/// like `Theme.spacing.md`. They are the pattern Lumo encourages.

import SwiftUI

struct BadScreen: View {
    var body: some View {
        VStack {
            // ← undersized_tap_target (32pt × 32pt < 44pt HIG min)
            Button(action: {}) { Image(systemName: "xmark") }
                .frame(width: 32, height: 32)

            // ← hardcoded_color (#B20000)
            Rectangle().fill(Color(red: 0.7, green: 0, blue: 0))

            // Counter — must NOT flag.
            Rectangle().fill(Color("brandPrimary"))
            Rectangle().fill(Color.red)

            // ← off_scale_radius (13 ∉ default scale)
            Rectangle().cornerRadius(13)
            Rectangle().cornerRadius(12)   // counter — on scale, fine
        }
        .padding(16)  // on scale — fine
    }
}
