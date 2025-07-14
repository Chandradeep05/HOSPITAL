function sendForm(formId, endpoint) {
    const form = document.getElementById(formId);
    form.addEventListener("submit", function (e) {
        e.preventDefault();
        const data = new FormData(form);
        const jsonData = Object.fromEntries(data.entries());
        fetch(endpoint, {
            method: "POST",
            body: JSON.stringify(jsonData),
            headers: { "Content-Type": "application/json" }
        })
        .then(res => res.json())
        .then(data => alert(data.message || JSON.stringify(data)))
        .catch(err => alert("Error: " + err));
    });
}

sendForm("patientForm", "/add_patient");
sendForm("doctorForm", "/add_doctor");
sendForm("workerForm", "/add_worker");

function getData(type) {
    fetch(`/get_all/${type}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("output").textContent = JSON.stringify(data, null, 2);
        });
}
