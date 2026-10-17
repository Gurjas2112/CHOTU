import 'package:flutter/material.dart';

/// CHOTU palette: navy background, cyan and magenta accents.
class C {
  static const bg = Color(0xFF090D16);
  static const surface = Color(0xFF111A2B);
  static const surfaceHi = Color(0xFF18243A);
  static const stroke = Color(0xFF233451);
  static const cyan = Color(0xFF00E5FF);
  static const magenta = Color(0xFFFF46C8);
  static const amber = Color(0xFFFFBE00);
  static const green = Color(0xFF5AFF78);
  static const red = Color(0xFFFF5A5A);
  static const text = Color(0xFFEAF2FF);
  static const dim = Color(0xFF8A9BB8);
}

ThemeData chotuTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: C.cyan,
    brightness: Brightness.dark,
    primary: C.cyan,
    secondary: C.magenta,
    surface: C.surface,
    background: C.bg,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: C.bg,
    appBarTheme: const AppBarTheme(
      backgroundColor: C.bg,
      foregroundColor: C.text,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: C.text, letterSpacing: 0.5),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: C.surface,
      indicatorColor: C.cyan.withOpacity(0.18),
      labelTextStyle: MaterialStateProperty.all(const TextStyle(fontSize: 11, color: C.dim)),
      iconTheme: MaterialStateProperty.resolveWith(
          (s) => IconThemeData(color: s.contains(MaterialState.selected) ? C.cyan : C.dim)),
    ),
    cardTheme: CardTheme(
      color: C.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: const BorderSide(color: C.stroke)),
    ),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(color: C.text, fontWeight: FontWeight.w800),
      titleMedium: TextStyle(color: C.text, fontWeight: FontWeight.w700),
      bodyMedium: TextStyle(color: C.text),
      bodySmall: TextStyle(color: C.dim),
    ),
  );
}
