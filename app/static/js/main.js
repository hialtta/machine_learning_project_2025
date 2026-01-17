
(function ($) {
    "use strict";


    /*==================================================================
    [ Validate ]*/
    var input = $('.validate-input .input100');
    var inputFile = $('.validate-input .input100-file');

    $('.validate-form').on('submit', function () {
        var check = true;

        for (var i = 0; i < input.length; i++) {
            if (validate(input[i]) == false) {
                showValidate(input[i]);
                check = false;
            }
        }

        for (var i = 0; i < inputFile.length; i++) {
            if (validate(inputFile[i]) == false) {
                showValidate(inputFile[i]);
                check = false;
            }
        }

        return check;
    });


    $('.validate-form .input100').each(function () {
        $(this).focus(function () {
            hideValidate(this);
        });
    });

    $('.validate-form .input100-file').each(function () {
        $(this).focus(function () {
            hideValidate(this);
        });
    });

    $("#uploadCV").on("submit", function (e) {
        e.preventDefault();

        let formData = new FormData(this);

        $.ajax({
            url: "/api/upload_pdf",
            type: "POST",
            data: formData,
            processData: false, // jangan ubah FormData ke string
            contentType: false, // biarkan browser set multipart/form-data
            success: function (response) {
                const base64String = response.file_base64;
                const doc_id = response.doc_id;
                console.log(doc_id)
                $.ajax({
                    url: '/api/extract_pdf',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ pdf_base64: base64String }),
                    success: function (response2) {
                        console.log(doc_id)
                        if (response2.status === 'success') {
                            const extracted_text = response2.extracted_text;
                            $.ajax({
                                url: '/api/extract_cv_info',
                                method: 'POST',
                                contentType: 'application/json',
                                data: JSON.stringify({ extracted_text: extracted_text }),
                                beforeSend: function () {
                                    // Tampilkan animasi loading
                                    $("#loadingSpinner").fadeIn();
                                },
                                success: function (response3) {
                                    console.log(doc_id)
                                    if (response3.result.done === true) {
                                        let final_extraction = JSON.parse(response3.result.response);
                                        let keywords = final_extraction.Keywords
                                        let responsibilities = final_extraction.Responsibilities
                                        let skills = final_extraction.Skills
                                        let yearsOfExperience = final_extraction.YearsOfExperience
                                        $.ajax({
                                            url: '/api/insert_cv_info',
                                            method: 'POST',
                                            contentType: 'application/json',
                                            data: JSON.stringify({ extracted_text: extracted_text, keywords, responsibilities, skills, yearsOfExperience, doc_id: doc_id }),
                                            success: function (response4) {
                                                if (response4.status === 'success') {
                                                    console.log('insert berhasil ' + response4)
                                                    $.ajax({
                                                        url: '/api/save_recommendation',
                                                        method: 'POST',
                                                        contentType: 'application/json',
                                                        data: JSON.stringify({
                                                            recommendations: response4.result.Top_Job_Titles.map(item => {
                                                                const query = encodeURIComponent(item.Title);
                                                                return {
                                                                    Title: item.Title,
                                                                    Confidence: item.Confidence,
                                                                    jobstreet: `https://id.jobstreet.com/id/${query}-jobs`,
                                                                    linkedin: `https://www.linkedin.com/jobs/search/?keywords=${query}`,
                                                                    indeed: `https://id.indeed.com/jobs?q=${query}`
                                                                };
                                                            })
                                                        }),
                                                        success: function (response5) {
                                                            if (response5.status === 'ok') {
                                                                // redirect ke page rekomendasi setelah disimpan di server
                                                                window.location.href = "/recommendation_list";
                                                                console.log(response4.Top_Job_Titles);
                                                            } else {
                                                                alert("Gagal menyimpan rekomendasi.");
                                                            }
                                                        },
                                                        error: function (xhr) {
                                                            alert("Error saat menyimpan rekomendasi: " + xhr.responseText);
                                                        }
                                                    });
                                                } else {
                                                    alert('Terjadi kesalahan: ' + response4.message);
                                                }
                                            },
                                            error: function (xhr) {
                                                alert('Error: ' + xhr.responseText);
                                            }
                                        });
                                    } else {
                                        alert('Terjadi kesalahan: ' + response3.message);
                                    }
                                },
                                error: function (xhr) {
                                    alert('Error: ' + xhr.responseText);
                                },
                                complete: function () {
                                    // Sembunyikan animasi setelah selesai (baik success/error)
                                    $("#loadingSpinner").fadeOut();
                                }
                            });
                            // alert(response2.extracted_text);
                        } else {
                            alert('Terjadi kesalahan: ' + response2.message);
                        }
                    },
                    error: function (xhr) {
                        alert('Error: ' + xhr.responseText);
                    }
                });
                // alert(JSON.stringify(response, null, 2));
            },
            error: function (xhr, status, error) {
                alert("Error: " + xhr.responseText);
            }
        });
    });

    if ($("#tableDoc").length) {
        $.ajax({
            url: "/api/documents",
            type: "GET",
            success: function (response) {
                let tbody = $("#tableDoc");
                tbody.empty();

                if (response.status === "success" && response.count > 0) {
                    response.data.forEach(function (doc, index) {
                        tbody.append(`
                            <tr>
                                <td>${index + 1}</td>
                                <td hidden>${doc.doc_id}</td>
                                <td>${doc.file_name}.${doc.extension}</td>
                                <td>${doc.uploaded_date}</td>
                                <td>${doc.uploaded_by}</td>
                                <td>
                                    <button class="btn btn-sm btn-primary view-doc" data-id="view${doc.doc_id}">
                                        View
                                    </button>
                                    <button class="btn btn-sm btn-danger delete-doc" data-id="delete${doc.doc_id}">
                                        Delete
                                    </button>
                                </td>
                            </tr>
                        `);
                    });
                } else {
                    tbody.append(`<tr><td colspan="5" class="text-center">No CVs found</td></tr>`);
                }
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
                alert("Gagal mengambil data CVs");
            }
        });
    }

    // if ($("#tableRec").length) {
    //     $.ajax({
    //         url: "/api/recommendation",
    //         type: "GET",
    //         success: function (response) {
    //             let tbody = $("#tableDoc");
    //             tbody.empty();

    //             if (response.status === "success" && response.count > 0) {
    //                 response.data.forEach(function (doc, index) {
    //                     tbody.append(`
    //                         <tr>
    //                             <td>${index + 1}</td>
    //                             <td hidden>${doc.doc_id}</td>
    //                             <td>${doc.file_name}.${doc.extension}</td>
    //                             <td>${doc.uploaded_date}</td>
    //                             <td>${doc.uploaded_by}</td>
    //                             <td>
    //                                 <button class="btn btn-sm btn-primary view-doc" data-id="view${doc.doc_id}">
    //                                     View
    //                                 </button>
    //                                 <button class="btn btn-sm btn-danger delete-doc" data-id="delete${doc.doc_id}">
    //                                     Delete
    //                                 </button>
    //                             </td>
    //                         </tr>
    //                     `);
    //                 });
    //             } else {
    //                 tbody.append(`<tr><td colspan="5" class="text-center">No CVs found</td></tr>`);
    //             }
    //         },
    //         error: function (xhr, status, error) {
    //             console.error("Error:", error);
    //             alert("Gagal mengambil data CVs");
    //         }
    //     });
    // }

    // $("#searchTable").on("keyup", function () {
    //     var value = $(this).val().toLowerCase();
    //     $("#tableDoc tr").filter(function () {
    //         $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1)
    //     });
    // });

    $("#searchTable").on("keyup", function () {
        var value = $(this).val().toLowerCase();

        $("#tableRec tr").filter(function () {
            // ambil teks hanya dari kolom yang boleh dicari (file_name + uploaded_at)
            var text = $(this).find("td:eq(1)").text().toLowerCase();

            $(this).toggle(text.indexOf(value) > -1);
        });
    });

    function validate(input) {
        if ($(input).attr('type') == 'email' || $(input).attr('name') == 'email') {
            if ($(input).val().trim().match(/^([a-zA-Z0-9_\-\.]+)@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.)|(([a-zA-Z0-9\-]+\.)+))([a-zA-Z]{1,5}|[0-9]{1,3})(\]?)$/) == null) {
                return false;
            }
        } else if ($(input).attr('type') == 'file' || $(input).attr('name') == 'file_pdf') {
            if (!$(input).val().includes('.pdf')) {
                return false;
            }
        } else {
            if ($(input).val().trim() == '') {
                return false;
            }
        }
    }

    function showValidate(input) {
        var thisAlert = $(input).parent();

        $(thisAlert).addClass('alert-validate');
    }

    function hideValidate(input) {
        var thisAlert = $(input).parent();

        $(thisAlert).removeClass('alert-validate');
    }


})(jQuery);