module.exports = {
    apps: [
        {
            name: 'Grade Huh Moe backend',
            script: 'uvicorn main:app --host 0.0.0.0 --port 24702',
            log_date_format: 'YYYY-MM-DD HH:mm:ss',
        },
    ],
};
