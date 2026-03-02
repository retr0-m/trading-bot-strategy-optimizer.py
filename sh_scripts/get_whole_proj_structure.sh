find . -type f \( -name "*.py" -o -name "*.html" -o -name "*.txt" \) | grep -v __pycache__ | grep -v ".venv" | grep -v ".vvv" | sort | while read f; do
    echo "===== $f =====" >> prompt.txt
    cat "$f" >> prompt.txt
    echo -e "\n" >> prompt.txt
done