function loadingBars() {
    jQuery(".loading-bar").each(function() {
        var text = jQuery(this).html();
        if (text.length < 4) {
            text = text + ".";
        } else {
            text = ".";
        }
        jQuery(this).html(text);
    });
    setTimeout(loadingBars, 500);
}

function reposUl(repos) {
    var ul = jQuery("<ul>");
    for(var i = 0; i < repos.length; i += 1) {
        var repo = repos[i];
        var name = repo["name"];
        var description = repo["description"];
        var li = jQuery("<li>").html(name + " - " + description);
        jQuery(".repos").append(li);
    }
    return ul;
}

function loadUserData() {
    jQuery.ajax({
        url: "/user_data",
        dataType: "json",
        success: function(data) {
            jQuery(".no-user").hide();
            jQuery(".handle").html(data["handle"]);
            jQuery(".repos").html();
            jQuery(".repos").append(reposUl(data["repos"]));
            for(var i = 0; i < data["orgs"].length; i += 1) {
                var org = data["orgs"][i];
                if (org["repos"].length) {
                    jQuery(".repos").append(jQuery("<h3>").html(org["handle"]));
                    jQuery(".repos").append(reposUl(org["repos"]));
                }
            }
            jQuery(".yes-user").show();
        }
    });
}

jQuery(function() {
    loadingBars();
});
