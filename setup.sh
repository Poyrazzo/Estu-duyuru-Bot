#!/usr/bin/env bash
set -e

echo "=== ESTÜ OYS Duyuru Botu Kurulum ==="

VENV_DIR="$(dirname "$0")/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] Sanal ortam oluşturuluyor..."
    python3 -m venv "$VENV_DIR"
fi

echo "[2/3] Bağımlılıklar yükleniyor..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$(dirname "$0")/requirements.txt" -q

echo "[3/3] Kurulum tamamlandı."
echo ""
echo "Sonraki adımlar:"
echo "  1. config.json dosyasını düzenleyin:"
echo "     - telegram.api_token  → @BotFather'dan aldığınız token"
echo "     - telegram.chat_id    → Kendi chat ID'niz"
echo "     - oys.moodle_session  → Tarayıcıdan kopyaladığınız MoodleSession çerezi"
echo "     - oys.course_ids      → Forum ID listesi (boş bırakırsanız sadece dashboard taranır)"
echo ""
echo "  2. Botu başlatın:"
echo "     ./run.sh"
echo ""
echo "MoodleSession nasıl alınır:"
echo "  1. Tarayıcıda OYS'a giriş yapın"
echo "  2. F12 → Application (veya Storage) → Cookies → oys.eskisehir.edu.tr"
echo "  3. 'MoodleSession' satırının Value sütununu kopyalayın"
