/// Fora da web não há barra de endereço: nada a limpar.
///
/// O APK sequer recebe o parâmetro (`Uri.base` não traz query no mobile), então este no-op
/// é o comportamento correto — e não um "ainda não implementado".
void scrubQueryParam(String name) {}
