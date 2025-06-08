document.addEventListener("DOMContentLoaded", function () {
    const consentButton = document.getElementById("aceitoBtn");
    consentButton.addEventListener("click", function () {
        document.getElementById('lgpdModal').style.display = 'none';
        document.getElementById('quiz-form').style.display = 'block';
    });
});
